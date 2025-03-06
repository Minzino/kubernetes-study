# 멀티 클러스터 Thanos HA 구축 가이드 (전체 가이드)

이 가이드는 다음의 내용을 포함합니다.

1. **클러스터 생성**
    - Kind를 사용하여 4개의 클러스터( mgmt, biz1, biz2, minio )를 각각 control-plane 1대와 worker 3대로 구성합니다.
2. **Persistent Volume(PV) 사용에 대한 설명 (선택 사항)**
    - Grafana와 같이 상태를 유지해야 하는 애플리케이션은 Pod 재시작 시에도 데이터(대시보드, 설정 등)가 보존되도록 PV를 사용합니다.
    - 동적 프로비저닝(클러스터에 이미 존재하는 StorageClass 사용)과 수동 프로비저닝(hostPath 또는 NFS 사용)의 예시를 함께 제공합니다.
3. **애플리케이션 배포**
    - **minio 클러스터:** 외부 스토리지 역할을 수행하는 MinIO를 NodePort 방식으로 배포합니다.
    - **biz 클러스터 (biz1, biz2):** 고객사가 직접 확인하는 클러스터로, Prometheus, Grafana(자체 조회용, PV 부착) 및 Thanos 사이드카(및 필요 시 Thanos Shipper)를 배포하여 메트릭 데이터를 MinIO에 전송합니다.
    - **mgmt 클러스터:** Prometheus‑Stack(내부 Grafana, PV 부착)과 Thanos 핵심 컴포넌트를 배포하여 biz 클러스터의 메트릭 데이터를 통합 조회합니다.
4. **Thanos 구성**
    - mgmt 클러스터의 Thanos Query는 biz 클러스터의 **프로메테우스가 배포되어있는 Node IP**(즉, Prometheus 사이드카의 외부 노출 IP)와 mgmt 내부 Store Gateway를 등록하여 메트릭을 통합 조회합니다.

> 중요 참고사항:
>
> - 각 클러스터의 노드 IP는 Kind 클러스터 생성 시 Docker에 의해 동적으로 할당됩니다. 실제 IP는 `kubectl get nodes -o wide` 명령으로 확인한 후, 각 values 파일 내의 `<minio-cluster-IP>`, `<mgmt-query-IP>` 등으로 교체해야 합니다.
> - 본 가이드는 기본적으로 동적 프로비저닝을 가정하지만, 동적 프로비저닝이 지원되지 않는 환경에서는 수동 프로비저닝(hostPath 또는 NFS) 방법을 참고하시기 바랍니다.

---

## 1. 클러스터 생성

Kind를 사용하여 4개의 클러스터를 생성합니다. 각 클러스터는 **control-plane 1대**와 **worker 3대**로 구성됩니다.

### 1.1. Kind 클러스터 생성 파일

### mgmt 클러스터 (kind-mgmt.yaml)

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    image: kindest/node:v1.29.7
  - role: worker
    image: kindest/node:v1.29.7
  - role: worker
    image: kindest/node:v1.29.7
  - role: worker
    image: kindest/node:v1.29.7

```

### biz1 클러스터 (kind-biz1.yaml)

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    image: kindest/node:v1.29.7
  - role: worker
    image: kindest/node:v1.29.7
  - role: worker
    image: kindest/node:v1.29.7
  - role: worker
    image: kindest/node:v1.29.7

```

### biz2 클러스터 (kind-biz2.yaml)

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    image: kindest/node:v1.29.7
  - role: worker
    image: kindest/node:v1.29.7
  - role: worker
    image: kindest/node:v1.29.7
  - role: worker
    image: kindest/node:v1.29.7

```

### minio 클러스터 (kind-minio.yaml)

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    image: kindest/node:v1.29.7
  - role: worker
    image: kindest/node:v1.29.7
  - role: worker
    image: kindest/node:v1.29.7
  - role: worker
    image: kindest/node:v1.29.7

```

### 1.2. 클러스터 생성 명령

아래 명령어를 통해 각 클러스터를 생성합니다.

```bash
kind create cluster --name mgmt --config kind-mgmt.yaml
kind create cluster --name biz1 --config kind-biz1.yaml
kind create cluster --name biz2 --config kind-biz2.yaml
kind create cluster --name minio --config kind-minio.yaml

```

각 클러스터는 kubeconfig에 `kind-mgmt`, `kind-biz1`, `kind-biz2`, `kind-minio`라는 컨텍스트로 생성됩니다.

---

## 2. Persistent Volume(PV) 사용에 대한 상세 설명 (선택 사항)

Grafana와 같이 상태를 유지해야 하는 애플리케이션은 Pod 재시작 시에도 데이터(대시보드, 설정 등)가 보존되도록 PV를 사용합니다.

### 2.1. 동적 프로비저닝

- 클러스터에 이미 존재하는 StorageClass(예: "standard" 또는 "local-path")를 지정하면, PVC가 생성될 때 클러스터가 자동으로 PV를 할당합니다.
- Helm values 파일에서 `persistence.storageClass`에 해당 StorageClass 이름을 입력합니다.

### 2.2. 수동 프로비저닝

동적 프로비저닝이 지원되지 않는 환경에서는 hostPath 또는 NFS를 사용하여 미리 PV와 PVC를 생성해야 합니다.

### 2.2.1. hostPath 예시

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: grafana-pv-hostpath
spec:
  capacity:
    storage: 10Gi
  accessModes:
    - ReadWriteOnce
  hostPath:
    path: /mnt/data/grafana   # 호스트 머신의 실제 경로
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: grafana-pvc-hostpath
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  storageClassName: ""   # hostPath PV는 StorageClass 없이 사용

```

### 2.2.2. NFS 예시

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: grafana-pv-nfs
spec:
  capacity:
    storage: 10Gi
  accessModes:
    - ReadWriteOnce
  nfs:
    server: <NFS-서버-IP>   # NFS 서버 IP
    path: /exported/path    # NFS 서버에서 공유하는 경로
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: grafana-pvc-nfs
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  storageClassName: ""   # NFS PV는 StorageClass 없이 사용하거나 별도 지정

```

> 참고:
>
>
> 만약 수동 PV/PVC를 사용하는 경우 Helm 차트의 `grafana.persistence.existingClaim` 옵션을 사용하여 PVC 이름(예: `grafana-pvc-hostpath` 또는 `grafana-pvc-nfs`)을 지정할 수 있습니다.
>

---

## 3. 애플리케이션 배포

### 3.1. minio 클러스터 – 외부 스토리지 배포

minio 클러스터는 모든 클러스터가 참조할 외부 스토리지 역할을 합니다.

### 3.1.1. 네임스페이스 생성 및 컨텍스트 전환

```bash
kubectl config use-context kind-minio
kubectl create namespace minio
kubectl create namespace monitoring

```

### 3.1.2. MinIO 배포 파일 (values-minio.yaml)

```yaml
mode: standalone

auth:
  rootUser: admin
  rootPassword: "admin1234"

defaultBuckets: "thanos"

replicaCount: 1

service:
  type: NodePort
  nodePorts:
    api: 32000
    console: 32001

```

배포:

```bash
helm install minio minio/minio -f values-minio.yaml -n minio

```

### 3.1.3. MinIO 접속 정보 파일 (minio-key.yaml)

이 파일은 biz 클러스터에서도 Secret으로 생성합니다.

```yaml
type: s3
config:
  bucket: thanos
  endpoint: <minio-cluster-IP>:32000   # 예: 172.18.0.10:32000. 실제 minio 클러스터의 control-plane IP로 변경.
  access_key: admin
  secret_key: admin1234
  insecure: true
  signature_version2: true

```

Secret 생성 예시 (biz1 클러스터):

```bash
kubectl config use-context kind-biz1
kubectl create namespace monitoring
kubectl create secret generic thanos-minio-secret -n monitoring --from-file=minio-key.yaml

```

biz2 클러스터에서도 동일하게 Secret을 생성합니다.

---

### 3.2. biz 클러스터 – Prometheus, Grafana 및 Thanos 사이드카 배포

biz 클러스터는 고객사가 직접 확인하는 클러스터입니다. 여기에서는 Prometheus, Grafana(자체 조회용, PV 부착) 및 Thanos 사이드카(필요 시 Thanos Shipper)를 배포하여 메트릭 데이터를 MinIO로 전송합니다.

### 3.2.1. 네임스페이스 생성 및 컨텍스트 전환 (biz1 예시)

```bash
kubectl config use-context kind-biz1
kubectl create namespace monitoring

```

### 3.2.2. kube‑prometheus‑stack 배포 – biz1용 values 파일 (values-kube-prometheus-stack.yaml)

```yaml
alertmanager:
  enabled: true

grafana:
  enabled: true
  defaultDashboardsTimezone: Asia/Seoul
  adminPassword: admin1234
  persistence:
    enabled: true
    storageClass: "standard"   # 클러스터에 동적 프로비저닝(StorageClass 이름) 사용. 동적 프로비저닝이 안되는 경우 수동 PV 예시 참고.
    accessModes:
      - ReadWriteOnce
    size: 10Gi

prometheus:
  thanosService:
    enabled: true
    type: NodePort
    clusterIP: ""
    nodePort: 31000  # Prometheus 사이드카가 외부에 노출되는 포트

  prometheusSpec:
    replicas: 1
    retention: 5d
    retentionSize: "10GiB"
    scrapeInterval: "15s"
    externalLabels:
      cluster: biz1  # biz1 클러스터 고유 레이블
    thanos:
      image: "quay.io/thanos/thanos:v0.31.0"
      objectStorageConfig:
        existingSecret:
          name: thanos-minio-secret
          key: minio-key.yaml
      version: v0.31.0
    additionalScrapeConfigs:
      - job_name: 'minio-metrics'
        metrics_path: /minio/v2/metrics/cluster
        static_configs:
          - targets: ['<minio-cluster-IP>:32000']

```

*(biz2 클러스터는 동일 파일을 사용하되, `externalLabels` 값을 `cluster: biz2`로 수정합니다.)*

배포:

```bash
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack -f values-kube-prometheus-stack.yaml -n monitoring

```

---

### 3.3. mgmt 클러스터 – Prometheus‑Stack(내부 Grafana, PV 부착) 및 Thanos 배포

mgmt 클러스터는 두 가지 역할을 수행합니다.

1. **Prometheus‑Stack 배포**
    - mgmt 클러스터에서는 Grafana와 Prometheus가 함께 배포됩니다.
    - Grafana는 Thanos Query를 데이터소스로 설정하여 통합 대시보드를 구성합니다.
2. **Thanos 구성 배포**
    - Thanos Query는 biz 클러스터의 **프로메테우스가 배포되어있는 Node IP**(즉, Prometheus 사이드카의 외부 노출 IP)와 mgmt 내부의 Store Gateway를 등록하여 메트릭을 통합 조회합니다.

### 3.3.1. 네임스페이스 생성 및 컨텍스트 전환 (mgmt 클러스터)

```bash
kubectl config use-context kind-mgmt
kubectl create namespace monitoring

```

### 3.3.2. Prometheus‑Stack 배포 – mgmt용 values 파일 (values-kube-prometheus-stack-mgmt.yaml)

```yaml
alertmanager:
  enabled: true

grafana:
  enabled: true
  defaultDashboardsTimezone: Asia/Seoul
  adminPassword: admin1234
  persistence:
    enabled: true
    storageClass: "standard"   # 동적 프로비저닝 환경: 클러스터에 존재하는 StorageClass 이름. 동적 프로비저닝이 안되는 경우 수동 PV 예시 참고.
    accessModes:
      - ReadWriteOnce
    size: 10Gi
  additionalDataSources:
    - name: Thanos
      type: prometheus
      access: proxy
      url: http://<mgmt-query-IP>:9091   # mgmt 클러스터의 Thanos Query 외부 접근 주소 (NodePort 또는 Ingress)
      isDefault: false
      editable: true

prometheus:
  prometheusSpec:
    replicas: 1
    retention: 5d
    retentionSize: "10GiB"
    scrapeInterval: "15s"
  externalLabels:
    cluster: mgmt

```

배포:

```bash
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack -f values-kube-prometheus-stack-mgmt.yaml -n monitoring

```

### 3.3.3. Thanos 배포 – mgmt 클러스터 (values-thanos.yaml)

```yaml
objstoreConfig: |-
  type: s3
  config:
    bucket: thanos
    endpoint: <minio-cluster-IP>:32000   # 실제 minio 클러스터의 외부 IP와 포트로 수정
    access_key: admin
    secret_key: admin1234
    insecure: true
    signature_version2: true

query:
  enabled: true
  # biz 클러스터의 프로메테우스가 배포되어있는 Node IP (Prometheus 사이드카가 외부에 노출된 Node IP)
  stores:
    - 172.21.0.4:31000   # biz1 클러스터: Prometheus 사이드카가 노출된 Node IP (예: biz1-control-plane)
    - 172.21.0.6:31000   # biz1 클러스터: 추가 Prometheus 노드 IP (필요 시 단일 주소만 사용)
    - 172.21.0.9:31000   # biz2 클러스터: Prometheus 사이드카가 노출된 Node IP (예: biz2-control-plane)
    - 172.21.0.10:31000  # biz2 클러스터: 추가 Prometheus 노드 IP (필요 시 단일 주소만 사용)
    - thanos-storegateway.monitoring.svc.cluster.local:10901  # mgmt 클러스터 내부 Store Gateway
  replicaCount: 2
  service:
    type: NodePort
    nodePorts:
      grpc: 30901
      http: 30902
  replicaLabel: prometheus_replica

bucketweb:
  enabled: true

compactor:
  enabled: true

storegateway:
  enabled: true

ruler:
  enabled: true
  alertmanagers:
    - http://alertmanager.monitoring.svc.cluster.local:9093
  config: |-
    groups:
    - name: default
      rules: []

```

배포:

```bash
helm install thanos bitnami/thanos --version 15.13.0 -f values-thanos.yaml -n monitoring --create-namespace

```

> 주의:
>
>
> mgmt 클러스터의 Thanos Query 서비스는 NodePort 또는 Ingress 방식으로 외부에 노출되어야 하며, Grafana의 데이터소스 URL(`<mgmt-query-IP>:9091`)에 반영되어야 합니다.
>

---

## 4. 수동 Persistent Volume(PV) 생성 파일 (선택 사항)

동적 프로비저닝이 지원되지 않는 환경에서는 Grafana와 같이 상태를 유지해야 하는 애플리케이션을 위해 PV와 PVC를 미리 생성합니다.

### 4.1. hostPath 방식 (grafana-pv-hostpath.yaml)

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: grafana-pv-hostpath
spec:
  capacity:
    storage: 10Gi
  accessModes:
    - ReadWriteOnce
  hostPath:
    path: /mnt/data/grafana   # 호스트 머신의 실제 경로
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: grafana-pvc-hostpath
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  storageClassName: ""

```

적용:

```bash
kubectl apply -f grafana-pv-hostpath.yaml -n <Grafana가 배포된 네임스페이스>

```

### 4.2. NFS 방식 (grafana-pv-nfs.yaml)

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: grafana-pv-nfs
spec:
  capacity:
    storage: 10Gi
  accessModes:
    - ReadWriteOnce
  nfs:
    server: <NFS-서버-IP>   # NFS 서버 IP
    path: /exported/path    # NFS 서버에서 공유하는 경로
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: grafana-pvc-nfs
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  storageClassName: ""

```

적용:

```bash
kubectl apply -f grafana-pv-nfs.yaml -n <Grafana가 배포된 네임스페이스>

```

> 참고:
>
>
> 만약 수동 PV/PVC를 사용하는 경우 Helm 차트의 `grafana.persistence.existingClaim` 옵션을 사용하여 PVC 이름(예: `grafana-pvc-hostpath` 또는 `grafana-pvc-nfs`)을 지정할 수 있습니다.
>

---

## 5. 네트워크 연결 및 테스트

### 5.1. biz 클러스터의 Prometheus 사이드카 테스트 (mgmt 클러스터에서)

mgmt 클러스터에서 임시 Pod를 생성하여 biz 클러스터의 Prometheus 사이드카(NodePort 31000)에 접근 가능한지 확인합니다.

```bash
kubectl config use-context kind-mgmt
kubectl run -it --rm busybox --image=busybox --restart=Never -- /bin/sh

```

Pod 내부에서 다음 명령을 실행합니다:

```
wget -qO- http://172.21.0.4:31000/metrics
wget -qO- http://172.21.0.6:31000/metrics
wget -qO- http://172.21.0.9:31000/metrics
wget -qO- http://172.21.0.10:31000/metrics

```

### 5.2. mgmt 클러스터 Thanos Query UI 확인

mgmt 클러스터에서 Thanos Query UI(Port-forward 또는 Ingress)를 통해 접속한 후 “Stores” 탭에

- biz 클러스터의 Prometheus 사이드카(노출된 Node IP)가 등록되어 있는지,
- mgmt 내부 Store Gateway가 정상 등록되어 있는지 확인합니다.

---

## 6. 최종 검증 및 결론

1. **MinIO 클러스터:**
    - MinIO 서비스가 NodePort(32000)로 외부에 노출되고, minio-key.yaml의 endpoint가 정확하게 설정되었는지 확인합니다.
2. **biz 클러스터 (biz1, biz2):**
    - Prometheus 사이드카가 NodePort(31000)로 외부에 노출되고, 각 클러스터의 externalLabels가 올바르게 적용되어 mgmt 클러스터에서 중복 없이 인식되는지 확인합니다.
    - 각 biz 클러스터에는 Grafana가 배포되어 해당 클러스터의 Prometheus 메트릭을 조회하며, PV를 통해 대시보드와 설정 데이터가 보존됩니다.
3. **mgmt 클러스터:**
    - Prometheus‑Stack과 Thanos Query가 biz 클러스터의 **프로메테우스가 배포되어있는 Node IP**(즉, Prometheus 사이드카 외부 노출 IP)와 mgmt 내부 Store Gateway를 통합하여 메트릭을 조회할 수 있는지 확인합니다.
    - mgmt 클러스터의 Grafana는 Thanos Query를 데이터소스로 사용하여 통합 모니터링 대시보드를 구성합니다.
4. **PV 설정:**
    - Grafana의 PV가 올바르게 생성되어 Pod 재시작 후에도 대시보드 및 설정 데이터가 보존되는지 확인합니다.
    - 동적 프로비저닝이 가능한 경우 StorageClass를 지정하고, 그렇지 않다면 수동으로 생성한 PV/PVC를 사용합니다.

---

## 7. 전체 파일 목록

### 7.1. Kind 클러스터 생성 파일

- **kind-mgmt.yaml**

    ```yaml
    kind: Cluster
    apiVersion: kind.x-k8s.io/v1alpha4
    nodes:
      - role: control-plane
        image: kindest/node:v1.29.7
      - role: worker
        image: kindest/node:v1.29.7
      - role: worker
        image: kindest/node:v1.29.7
      - role: worker
        image: kindest/node:v1.29.7
    
    ```

- **kind-biz1.yaml**

    ```yaml
    kind: Cluster
    apiVersion: kind.x-k8s.io/v1alpha4
    nodes:
      - role: control-plane
        image: kindest/node:v1.29.7
      - role: worker
        image: kindest/node:v1.29.7
      - role: worker
        image: kindest/node:v1.29.7
      - role: worker
        image: kindest/node:v1.29.7
    
    ```

- **kind-biz2.yaml**

    ```yaml
    kind: Cluster
    apiVersion: kind.x-k8s.io/v1alpha4
    nodes:
      - role: control-plane
        image: kindest/node:v1.29.7
      - role: worker
        image: kindest/node:v1.29.7
      - role: worker
        image: kindest/node:v1.29.7
      - role: worker
        image: kindest/node:v1.29.7
    
    ```

- **kind-minio.yaml**

    ```yaml
    kind: Cluster
    apiVersion: kind.x-k8s.io/v1alpha4
    nodes:
      - role: control-plane
        image: kindest/node:v1.29.7
      - role: worker
        image: kindest/node:v1.29.7
      - role: worker
        image: kindest/node:v1.29.7
      - role: worker
        image: kindest/node:v1.29.7
    
    ```


### 7.2. MinIO 관련 파일

- **minio-key.yaml**

    ```yaml
    type: s3
    config:
      bucket: thanos
      endpoint: <minio-cluster-IP>:32000
      access_key: admin
      secret_key: admin1234
      insecure: true
      signature_version2: true
    
    ```

- **values-minio.yaml**

    ```yaml
    mode: standalone
    
    auth:
      rootUser: admin
      rootPassword: "admin1234"
    
    defaultBuckets: "thanos"
    
    replicaCount: 1
    
    service:
      type: NodePort
      nodePorts:
        api: 32000
        console: 32001
    
    ```


### 7.3. kube‑prometheus‑stack (biz 클러스터용 – biz1 예시; biz2는 externalLabels 변경)

- **values-kube-prometheus-stack.yaml**

    ```yaml
    alertmanager:
      enabled: true
    
    grafana:
      enabled: true
      defaultDashboardsTimezone: Asia/Seoul
      adminPassword: admin1234
      persistence:
        enabled: true
        storageClass: "standard"
        accessModes:
          - ReadWriteOnce
        size: 10Gi
    
    prometheus:
      thanosService:
        enabled: true
        type: NodePort
        clusterIP: ""
        nodePort: 31000
    
      prometheusSpec:
        replicas: 1
        retention: 5d
        retentionSize: "10GiB"
        scrapeInterval: "15s"
        externalLabels:
          cluster: biz1
        thanos:
          image: "quay.io/thanos/thanos:v0.31.0"
          objectStorageConfig:
            existingSecret:
              name: thanos-minio-secret
              key: minio-key.yaml
          version: v0.31.0
        additionalScrapeConfigs:
          - job_name: 'minio-metrics'
            metrics_path: /minio/v2/metrics/cluster
            static_configs:
              - targets: ['<minio-cluster-IP>:32000']
    
    ```


### 7.4. Prometheus‑Stack (mgmt 클러스터용)

- **values-kube-prometheus-stack-mgmt.yaml**

    ```yaml
    alertmanager:
      enabled: true
    
    grafana:
      enabled: true
      defaultDashboardsTimezone: Asia/Seoul
      adminPassword: admin1234
      persistence:
        enabled: true
        storageClass: "standard"
        accessModes:
          - ReadWriteOnce
        size: 10Gi
      additionalDataSources:
        - name: Thanos
          type: prometheus
          access: proxy
          url: http://<mgmt-query-IP>:9091
          isDefault: false
          editable: true
    
    prometheus:
      prometheusSpec:
        replicas: 1
        retention: 5d
        retentionSize: "10GiB"
        scrapeInterval: "15s"
      externalLabels:
        cluster: mgmt
    
    ```


### 7.5. Thanos (mgmt 클러스터용)

- **values-thanos.yaml**

    ```yaml
    objstoreConfig: |-
      type: s3
      config:
        bucket: thanos
        endpoint: <minio-cluster-IP>:32000
        access_key: admin
        secret_key: admin1234
        insecure: true
        signature_version2: true
    
    query:
      enabled: true
      stores:
        - 172.21.0.4:31000   # biz1 클러스터: Prometheus 사이드카가 노출된 Node IP (예: biz1-control-plane)
        - 172.21.0.6:31000   # biz1 클러스터: 추가 Prometheus 노드 IP (필요 시 단일 주소만 사용)
        - 172.21.0.9:31000   # biz2 클러스터: Prometheus 사이드카가 노출된 Node IP (예: biz2-control-plane)
        - 172.21.0.10:31000  # biz2 클러스터: 추가 Prometheus 노드 IP (필요 시 단일 주소만 사용)
        - thanos-storegateway.monitoring.svc.cluster.local:10901
      replicaCount: 2
      service:
        type: NodePort
        nodePorts:
          grpc: 30901
          http: 30902
      replicaLabel: prometheus_replica
    
    bucketweb:
      enabled: true
    
    compactor:
      enabled: true
    
    storegateway:
      enabled: true
    
    ruler:
      enabled: true
      alertmanagers:
        - http://alertmanager.monitoring.svc.cluster.local:9093
      config: |-
        groups:
        - name: default
          rules: []
    
    ```


### 7.6. 수동 PV 생성 파일 (선택 사항)

### 7.6.1. hostPath 방식 (grafana-pv-hostpath.yaml)

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: grafana-pv-hostpath
spec:
  capacity:
    storage: 10Gi
  accessModes:
    - ReadWriteOnce
  hostPath:
    path: /mnt/data/grafana
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: grafana-pvc-hostpath
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  storageClassName: ""

```

### 7.6.2. NFS 방식 (grafana-pv-nfs.yaml)

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: grafana-pv-nfs
spec:
  capacity:
    storage: 10Gi
  accessModes:
    - ReadWriteOnce
  nfs:
    server: <NFS-서버-IP>
    path: /exported/path
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: grafana-pvc-nfs
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  storageClassName: ""

```

---

## 8. 네트워크 연결 및 테스트

### 8.1. biz 클러스터의 Prometheus 사이드카 테스트 (mgmt 클러스터에서)

```bash
kubectl config use-context kind-mgmt
kubectl run -it --rm busybox --image=busybox --restart=Never -- /bin/sh

```

Pod 내부에서 다음 명령을 실행:

```
wget -qO- http://172.21.0.4:31000/metrics
wget -qO- http://172.21.0.6:31000/metrics
wget -qO- http://172.21.0.9:31000/metrics
wget -qO- http://172.21.0.10:31000/metrics

```

### 8.2. mgmt 클러스터 Thanos Query UI 확인

mgmt 클러스터에서 Thanos Query UI(Port-forward 또는 Ingress)를 통해 접속한 후 “Stores” 탭에

- biz 클러스터의 Prometheus 사이드카(노출된 Node IP)가 등록되어 있는지,
- mgmt 내부 Store Gateway가 정상 등록되어 있는지 확인합니다.

---

## 9. 최종 검증 및 결론

1. **MinIO 클러스터:**
    - MinIO 서비스가 NodePort(32000)로 외부에 노출되고, minio-key.yaml의 endpoint가 정확하게 설정되었는지 확인합니다.
2. **biz 클러스터 (biz1, biz2):**
    - Prometheus 사이드카가 NodePort(31000)로 외부에 노출되고, 각 클러스터의 externalLabels가 올바르게 적용되어 mgmt 클러스터에서 중복 없이 인식되는지 확인합니다.
    - 각 biz 클러스터에는 Grafana가 배포되어 해당 클러스터의 Prometheus 메트릭을 조회하며, PV를 통해 대시보드와 설정 데이터가 보존됩니다.
3. **mgmt 클러스터:**
    - Prometheus‑Stack과 Thanos Query가 biz 클러스터의 **프로메테우스가 배포되어있는 Node IP**(즉, Prometheus 사이드카의 외부 노출 IP)와 mgmt 내부 Store Gateway를 통합하여 메트릭을 조회할 수 있는지 확인합니다.
    - mgmt 클러스터의 Grafana는 Thanos Query를 데이터소스로 사용하여 통합 모니터링 대시보드를 구성합니다.
4. **PV 설정:**
    - Grafana의 PV가 올바르게 생성되어 Pod 재시작 후에도 대시보드와 설정 데이터가 보존되는지 확인합니다.
    - 동적 프로비저닝이 가능한 경우 StorageClass를 지정하고, 그렇지 않다면 수동 PV/PVC를 사용합니다.
