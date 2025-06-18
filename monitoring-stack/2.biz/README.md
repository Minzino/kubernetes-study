# 1. 사전 준비

- 네임스페이스 생성

```bash
kubectl create ns monitoring  # 그라파나, 프로메테우스, 로키가 배포될 네임스페이스
```

---

# 2. git repo에서 패키지 받아오기

- Backup 디렉토리 생성
- 패키지 파일 클론 (`develop/v3.0.5`)

```bash
mkdir backup ; cd backup 
git clone -b develop/v3.0.4 https://101.202.40.5:30000/Viola/viola-monitoring.git
```

---

`2. biz` 디렉토리 구성은 아래와 같으며 번호 순서대로 설치를 진행하시면 됩니다. 

```bash
drwxr-xr-x 4 root root  175 Jun 17 16:15 1.minio
drwxr-xr-x 4 root root  172 Jun 17 17:12 2.kube-prometheus-stack
drwxr-xr-x 4 root root  179 Jun 17 16:28 3.promtail
drwxr-xr-x 4 root root  130 Jun 17 17:00 4.loki-distriuted
```

# **3. kube-prometheus-stack Install**

- `kube-prometheus-stack : kube-prometheus-stack-66.4.0`

## 3-1. Values.yaml 수정

- persistence: storageClass: “수정”
- storageSpec: storageClass: “수정”
- node label 지정 : kubectl label nodes [NodeName] monitoring=true
- `kubeEtcd: endpoints`: “masterIP 수정”

```bash
grafana:
  persistence:
    enabled: true
    type: sts
    storageClassName: "수정"
    accessModes:
      - ReadWriteOnce
    size: 20Gi
    finalizers:
      - kubernetes.io/pvc-protection
      
prometheusSpec:
  nodeSelector:
    monitoring: "true"   
      
   storageSpec:
     volumeClaimTemplate:
       spec:
         storageClassName:  "수정" 
         accessModes: ["ReadWriteOnce"]
         resources:
           requests:
             storage: 50Gi
      
kubeEtcd:
  enabled: true
  ## If your etcd is not deployed as a pod, specify IPs it can be found on
  endpoints:
   - 10.10.0.101
   - 10.10.0.102
   - 10.10.0.103
```

---
## 3-2. ETCD Metrics 활성화
- 마스터 3대 접속 후 아래와 같이 추가 ( 프로메테우스 타겟을 잡기 위함 )
    - `vi /etc/systemd/system/etcd.service`
    - `--listen-metrics-urls=http://0.0.0.0:2381` 추가

```bash
[Unit]
Description=etcd (self made daemon)
Documentation=https://etcd.io/docs/

[Service]
Type=notify
User=root
EnvironmentFile=/etc/etcd/etcd.env
ExecStart=/usr/local/bin/etcd --listen-metrics-urls=http://0.0.0.0:2381
NotifyAccess=all
Restart=always
RestartSec=10s
LimitNOFILE=40000

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload 
systemctl restart etcd.service
systemctl status etcd.service
```

## 3-3. kube-proxy Metric 활성화
```bash
kubectl edit cm -n kube-system
```

```bash
kind: ConfigMap
apiVersion: v1
metadata:
  name: kube-proxy
  namespace: kube-system
data:
  config.conf: |
    # 기존 설정 예시
    clientConnection:
      kubeconfig: "/var/lib/kube-proxy/kubeconfig.conf" 
    .
    .
    .
    # metricsBindAddress 설정 변경
    metricsBindAddress: "0.0.0.0:10249"  # 추가만 하면 됌
    mode: ipvs
    nftables:
    ...
```

## 3-4. kube-scheduler Metric 활성화
- 마스터 3대 접속 후 아래와 같이 추가 ( 프로메테우스 타겟을 잡기 위함 )
    - `vi /etc/kubernetes/manifests/kube-scheduler.yaml`
    - `-bind-address 0.0.0.0` 으로 수정
```bash
kubectl edit cm -n kube-system
```

```bash
spec:
  containers:
  - command:
    - kube-scheduler
    - --bind-address=0.0.0.0   # 기존: --bind-address=127.0.0.1
    - --leader-elect=true

```
- **파일 저장 후 kube-scheduler 자동 재시작 확인**
    
    kube-scheduler는 static pod이므로, 파일 변경 후 자동으로 재기동됩니다.

## 3-5. kube-controller-manager Metric 활성화
- 마스터 3대 접속 후 아래와 같이 추가 ( 프로메테우스 타겟을 잡기 위함 )
    - `vi /etc/kubernetes/manifests/kube-controller-manager.yaml`
    - `-bind-address 0.0.0.0` 으로 수정

```bash
spec:
  containers:
  - command:
    - kube-controller-manager
    - --bind-address=0.0.0.0   # 기존: --bind-address=127.0.0.1
    - --allocate-node-cidrs=true

```



# 4. Promtail 설치

```bash
cd 3.loki-distriuted/
helm install promtail . -n monitoring 
```

---

# 5. Loki 설치

- cd 4.loki-distriuted
    - vi values.yaml

```yaml
global:
  dnsService: "kube-dns" # coredns or kube-dns 확인 후 수정

ingester:
  persistence:
    storageClass: "수정"
```

```yaml
helm install loki . -n monitoring 
```

---
