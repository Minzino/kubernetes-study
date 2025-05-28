import os
import subprocess
import time

# 정적 변수 설정
HELM_VERSION = "v3.9.4"
HELM_URL = f"https://get.helm.sh/helm-{HELM_VERSION}-linux-amd64.tar.gz"
HELM_BINARY = "/usr/bin/helm"
CILIUM_VERSION = "1.15.4"
CNI_NAMESPACE = "kube-system"
LOG_FILE = "/root/bastion_setup.log"
COREDNS_YAML_PATH = "/tmp/coredns.yaml"
COREDNS_IMAGE = "coredns/coredns:1.6.5"
CLUSTER_IP = "10.231.0.10"


# 로그 작성 함수
def log_message(message):
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    with open(LOG_FILE, "a", encoding="utf-8") as log:
        log.write(f"{timestamp} - {message}\n")
    print(message)


# 명령 실행 함수
def run_command(command, ignore_failure=False):
    try:
        result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        log_message(result.stdout.decode().strip())
    except subprocess.CalledProcessError as e:
        log_message(f"❌ 명령 실행 실패: {command}\n{e.stderr.decode().strip()}")
        if not ignore_failure:
            raise


# Helm 설치 함수
def install_helm():
    log_message("🔄 Helm 설치 중...")
    helm_tarball = "/tmp/helm.tar.gz"
    if not os.path.exists(HELM_BINARY):
        run_command(f"wget -q -O {helm_tarball} {HELM_URL}")
        run_command(f"tar -xvf {helm_tarball} -C /tmp")
        run_command(f"mv /tmp/linux-amd64/helm {HELM_BINARY}")
        log_message("✅ Helm 설치 완료")
    else:
        log_message("✅ Helm이 이미 설치되어 있습니다.")


# Cilium 설치 함수 (재설치 포함)
def install_cilium():
    log_message("🔄 Cilium 설치 중...")

    result = subprocess.run(f"helm list -n {CNI_NAMESPACE} | grep cilium", shell=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    if result.returncode == 0:
        log_message("⚠️ Cilium이 이미 설치되어 있습니다. 업데이트를 진행합니다...")
        run_command(
            f"helm upgrade --install cilium cilium/cilium --version {CILIUM_VERSION} --namespace {CNI_NAMESPACE} --create-namespace")
        log_message("✅ Cilium 업데이트 완료")
    else:
        log_message("🚀 Cilium 신규 설치 진행...")
        run_command("helm repo add cilium https://helm.cilium.io")
        run_command("helm repo update")
        run_command(
            f"helm install cilium cilium/cilium --version {CILIUM_VERSION} --namespace {CNI_NAMESPACE} --create-namespace")
        log_message("✅ Cilium 설치 완료")


# CoreDNS 배포 함수 (삭제 후 재설치)
def deploy_coredns():
    log_message("🔄 CoreDNS 배포 중...")

    # 기존 CoreDNS 제거
    log_message("🔍 기존 CoreDNS 확인 중...")
    result = subprocess.run("kubectl get deployment -n kube-system | grep coredns", shell=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)

    if result.returncode == 0:
        log_message("⚠️ CoreDNS가 이미 설치되어 있습니다. 기존 설치를 제거합니다...")
        run_command("kubectl delete deployment coredns -n kube-system", ignore_failure=True)
        run_command("kubectl delete service coredns -n kube-system", ignore_failure=True)
        run_command("kubectl delete configmap coredns -n kube-system", ignore_failure=True)
        run_command("kubectl delete clusterrolebinding system:coredns", ignore_failure=True)
        run_command("kubectl delete clusterrole system:coredns", ignore_failure=True)
        run_command("kubectl delete serviceaccount coredns -n kube-system", ignore_failure=True)
        log_message("✅ 기존 CoreDNS 제거 완료")

    # CoreDNS 새로 배포
    log_message("🔧 CoreDNS YAML 생성 중...")
    coredns_content = f"""---
apiVersion: v1
kind: ConfigMap
metadata:
  name: coredns
  namespace: kube-system
  labels:
      addonmanager.kubernetes.io/mode: EnsureExists
data:
  Corefile: |
    .:53 {{
        errors
        health {{
            lameduck 5s
        }}
        ready
        kubernetes cluster.local in-addr.arpa ip6.arpa {{
          pods insecure
          fallthrough in-addr.arpa ip6.arpa
        }}
        prometheus :9153
        forward . /etc/resolv.conf {{
          prefer_udp
        }}
        cache 30
        loop
        reload
        loadbalance
    }}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  annotations:
    rbac.authorization.kubernetes.io/autoupdate: "true"
  labels:
    kubernetes.io/bootstrapping: rbac-defaults
    addonmanager.kubernetes.io/mode: EnsureExists
  name: system:coredns
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: system:coredns
subjects:
  - kind: ServiceAccount
    name: coredns
    namespace: kube-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  labels:
    kubernetes.io/bootstrapping: rbac-defaults
    addonmanager.kubernetes.io/mode: Reconcile
  name: system:coredns
rules:
  - apiGroups:
      - ""
    resources:
      - endpoints
      - services
      - pods
      - namespaces
    verbs:
      - list
      - watch
  - apiGroups:
      - ""
    resources:
      - nodes
    verbs:
      - get
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: "coredns"
  namespace: kube-system
  labels:
    k8s-app: "kube-dns"
    addonmanager.kubernetes.io/mode: Reconcile
    kubernetes.io/name: "coredns"
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 10%
  selector:
    matchLabels:
      k8s-app: kube-dns
  template:
    metadata:
      labels:
        k8s-app: kube-dns
    spec:
      priorityClassName: system-cluster-critical
      nodeSelector:
        kubernetes.io/os: linux
      serviceAccountName: coredns
      tolerations:
        - key: node-role.kubernetes.io/master
          effect: NoSchedule
        - key: "CriticalAddonsOnly"
          operator: "Exists"
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
          - topologyKey: "kubernetes.io/hostname"
            labelSelector:
              matchLabels:
                k8s-app: kube-dns
        nodeAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            preference:
              matchExpressions:
              - key: node-role.kubernetes.io/master
                operator: In
                values:
                - ""
      securityContext:
        seccompProfile:
          type: RuntimeDefault
      containers:
      - name: coredns
        image: "{COREDNS_IMAGE}"
        imagePullPolicy: IfNotPresent
        resources:
          # TODO: Set memory limits when we've profiled the container for large
          # clusters, then set request = limit to keep this container in
          # guaranteed class. Currently, this container falls into the
          # "burstable" category so the kubelet doesn't backoff from restarting it.
          limits:
            memory: 170Mi
          requests:
            cpu: 100m
            memory: 70Mi
        args: [ "-conf", "/etc/coredns/Corefile" ]
        volumeMounts:
        - name: config-volume
          mountPath: /etc/coredns
        - name: tz-config
          mountPath: /etc/localtime
          readOnly: true
        ports:
        - containerPort: 53
          name: dns
          protocol: UDP
        - containerPort: 53
          name: dns-tcp
          protocol: TCP
        - containerPort: 9153
          name: metrics
          protocol: TCP
        securityContext:
          allowPrivilegeEscalation: false
          capabilities:
            add:
            - NET_BIND_SERVICE
            drop:
            - all
          readOnlyRootFilesystem: true
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
            scheme: HTTP
          timeoutSeconds: 5
          successThreshold: 1
          failureThreshold: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8181
            scheme: HTTP
          timeoutSeconds: 5
          successThreshold: 1
          failureThreshold: 10
      dnsPolicy: Default
      volumes:
        - name: config-volume
          configMap:
            name: coredns
            items:
            - key: Corefile
              path: Corefile
        - name: tz-config
          hostPath:
            path: /etc/localtime
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: coredns
  namespace: kube-system
  labels:
    addonmanager.kubernetes.io/mode: Reconcile
---
apiVersion: v1
kind: Service
metadata:
  name: coredns
  namespace: kube-system
  labels:
    k8s-app: kube-dns
    kubernetes.io/name: "coredns"
    addonmanager.kubernetes.io/mode: Reconcile
  annotations:
    prometheus.io/port: "9153"
    prometheus.io/scrape: "true"
spec:
  selector:
    k8s-app: kube-dns
  clusterIP: {CLUSTER_IP}
  ports:
    - name: dns
      port: 53
      protocol: UDP
    - name: dns-tcp
      port: 53
      protocol: TCP
    - name: metrics
      port: 9153
      protocol: TCP
"""

    with open(COREDNS_YAML_PATH, "w") as f:
        f.write(coredns_content.strip())

    run_command(f"kubectl apply -f {COREDNS_YAML_PATH}")
    log_message("✅ CoreDNS 배포 완료")


# 메인 함수
def main():
    log_message("=== Bastion 노드 Cilium 및 네트워크 설정 시작 ===")
    install_helm()
    install_cilium()
    deploy_coredns()
    log_message("=== Bastion 노드 설정 완료 ===")


if __name__ == "__main__":
    main()
