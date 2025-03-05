# 멀티 클러스터 Thanos HA 구축 가이드

이 문서는 Kind 클러스터( mgmt, biz1, biz2, minio )를 이용하여 멀티 클러스터 환경에서 Thanos HA를 구축하는 방법을 설명합니다.

- **mgmt 클러스터**: Thanos 핵심 컴포넌트(Query, Compactor, Store Gateway, Ruler 등)를 배포하여 여러 클러스터의 메트릭을 통합 조회합니다.
- **biz1, biz2 클러스터**: 각각 kube‑prometheus‑stack을 통해 Prometheus, Grafana 및 Thanos 사이드카를 배포합니다. 각 클러스터는 고유한 externalLabels(`cluster: biz1` 또는 `cluster: biz2`)를 설정하여 mgmt 클러스터의 Thanos Query에서 중복 없이 인식합니다.
- **minio 클러스터**: 독립적인 MinIO 전용 클러스터로, 외부 스토리지 역할을 하며 NodePort(예: 32000)를 통해 외부에서 접근합니다.
- **Thanos Query 설정 개선**: mgmt 클러스터의 Thanos Query는 biz 클러스터의 Prometheus 사이드카의 NodePort 엔드포인트를 stores에 등록하고, replicaLabel을 `prometheus_replica`로 설정하여 duplicate storeEndpoints 경고를 해결합니다.

> **참고**: 각 클러스터의 노드 IP는 Kind 클러스터 생성 시 Docker에 의해 동적으로 할당되므로, 실제 IP는 `kubectl get nodes -o wide` 명령으로 확인 후 values 파일에 반영해야 합니다.

---

## 1. 사전 준비

- **필수 도구**: Docker, Kind, kubectl, Helm
- **환경**: 테스트용 M1/M2 Mac 또는 Linux/Windows 환경

---

## 2. Kind 클러스터 생성

4개의 클러스터를 각각 생성합니다.

### 2.1. 클러스터 생성 파일

#### mgmt 클러스터 (kind-mgmt.yaml)
```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    image: kindest/node:v1.29.7
  - role: worker
    image: kindest/node:v1.29.7
```

#### biz1 클러스터 (kind-biz1.yaml)
```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    image: kindest/node:v1.29.7
  - role: worker
    image: kindest/node:v1.29.7
```

#### biz2 클러스터 (kind-biz2.yaml)
```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    image: kindest/node:v1.29.7
  - role: worker
    image: kindest/node:v1.29.7
```

#### minio 클러스터 (kind-minio.yaml)
```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    image: kindest/node:v1.29.7
  - role: worker
    image: kindest/node:v1.29.7
```

### 2.2. 클러스터 생성 명령
```bash
kind create cluster --name mgmt --config kind-mgmt.yaml
kind create cluster --name biz1 --config kind-biz1.yaml
kind create cluster --name biz2 --config kind-biz2.yaml
kind create cluster --name minio --config kind-minio.yaml
```

각 클러스터는 kubeconfig에 각각의 컨텍스트(`kind-mgmt`, `kind-biz1`, `kind-biz2`, `kind-minio`)로 생성됩니다.

---

## 3. 클러스터별 배포

### 3.1. minio 클러스터 (외부 스토리지)

#### 3.1.1. 컨텍스트 전환 및 네임스페이스 생성 (minio 클러스터)
```bash
kubectl config use-context kind-minio
kubectl create namespace minio
kubectl create namespace monitoring
```

#### 3.1.2. MinIO 배포 (values-minio.yaml)
**values-minio.yaml**
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

#### 3.1.3. MinIO 접속 정보 (minio-key.yaml)
MinIO의 endpoint는 minio 클러스터의 외부 노출된 IP와 NodePort를 사용합니다.  
**minio-key.yaml**
```yaml
type: s3
config:
  bucket: thanos
  endpoint: <minio-cluster-IP>:32000  # 예: 172.18.0.10:32000 (실제 minio 클러스터의 control-plane IP 확인)
  access_key: admin
  secret_key: admin1234
  insecure: true
  signature_version2: false
```
※ `<minio-cluster-IP>`는 `kubectl get nodes --context kind-minio -o wide`로 확인합니다.

**중요:** 이 secret은 biz 클러스터들( biz1, biz2 )에서 생성합니다.  
예시 (biz1 클러스터):
```bash
kubectl config use-context kind-biz1
kubectl create namespace monitoring
kubectl create secret generic thanos-minio-secret -n monitoring --from-file=minio-key.yaml
```
biz2 클러스터에서도 동일하게 secret을 생성합니다.

---

### 3.2. biz1 클러스터 배포 (Prometheus, Grafana, Thanos Sidecar)

#### 3.2.1. 컨텍스트 전환 및 네임스페이스 생성 (biz1 클러스터)
```bash
kubectl config use-context kind-biz1
kubectl create namespace monitoring
```

#### 3.2.2. kube‑prometheus‑stack 배포 (values-kube-prometheus-stack.yaml, biz1용)
**values-kube-prometheus-stack.yaml (biz1)**
```yaml
alertmanager:
  enabled: true

grafana:
  defaultDashboardsTimezone: Asia/Seoul
  adminPassword: admin1234
  additionalDataSources:
    - name: Thanos
      type: prometheus
      access: proxy
      # mgmt 클러스터의 Thanos Query 외부 접근 주소로 수정 (예: NodePort로 노출된 mgmt Thanos Query IP:9091)
      url: http://<mgmt-query-IP>:9091
      isDefault: false
      editable: true

prometheus:
  thanosService:
    enabled: true
    type: NodePort
    clusterIP: ""
    nodePort: 31000  # biz1 클러스터의 Prometheus Sidecar 외부 노출 포트

  prometheusSpec:
    replicas: 1
    retention: 5d
    retentionSize: "10GiB"
    scrapeInterval: "15s"

    externalLabels:
      cluster: biz1  # biz1 클러스터 고유 레이블

    thanos:
      image: "quay.io/thanos/thanos:v0.24.0"
      objectStorageConfig:
        existingSecret:
          name: thanos-minio-secret
          key: minio-key.yaml
      version: v0.24.0

    additionalScrapeConfigs:
      - job_name: 'minio-metrics'
        metrics_path: /minio/v2/metrics/cluster
        static_configs:
          - targets: ['<minio-cluster-IP>:32000']
```
※ `<minio-cluster-IP>`는 minio 클러스터의 외부 IP로 교체합니다.

배포:
```bash
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack -f values-kube-prometheus-stack.yaml -n monitoring
```

---

### 3.3. biz2 클러스터 배포 (Prometheus, Grafana, Thanos Sidecar)

biz2 클러스터는 biz1과 거의 동일하되, externalLabels를 `cluster: biz2`로 설정합니다.

#### 3.3.1. 컨텍스트 전환 및 네임스페이스 생성 (biz2 클러스터)
```bash
kubectl config use-context kind-biz2
kubectl create namespace monitoring
```

#### 3.3.2. kube‑prometheus‑stack 배포 (values-kube-prometheus-stack.yaml, biz2용)
**values-kube-prometheus-stack.yaml (biz2)**
```yaml
alertmanager:
  enabled: true

grafana:
  defaultDashboardsTimezone: Asia/Seoul
  adminPassword: admin1234
  additionalDataSources:
    - name: Thanos
      type: prometheus
      access: proxy
      url: http://<mgmt-query-IP>:9091
      isDefault: false
      editable: true

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
      cluster: biz2  # biz2 클러스터 고유 레이블

    thanos:
      image: "quay.io/thanos/thanos:v0.24.0"
      objectStorageConfig:
        existingSecret:
          name: thanos-minio-secret
          key: minio-key.yaml
      version: v0.24.0

    additionalScrapeConfigs:
      - job_name: 'minio-metrics'
        metrics_path: /minio/v2/metrics/cluster
        static_configs:
          - targets: ['<minio-cluster-IP>:32000']
```

배포:
```bash
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack -f values-kube-prometheus-stack.yaml -n monitoring
```

그리고 biz2 클러스터에서도 minio-key secret를 생성합니다.
```bash
kubectl create secret generic thanos-minio-secret -n monitoring --from-file=minio-key.yaml
```

---

### 3.4. mgmt 클러스터 배포 (Thanos 핵심 컴포넌트)

#### 3.4.1. 컨텍스트 전환 및 네임스페이스 생성 (mgmt 클러스터)
```bash
kubectl config use-context kind-mgmt
kubectl create namespace monitoring
```

#### 3.4.2. Thanos 배포 (values-thanos.yaml, mgmt)
**values-thanos.yaml (mgmt)**
```yaml
objstoreConfig: |-
  type: s3
  config:
    bucket: thanos
    # minio 클러스터의 외부 접근 주소
    endpoint: <minio-cluster-IP>:32000
    access_key: admin
    secret_key: admin1234
    insecure: true
    signature_version2: false

query:
  enabled: true
  # biz 클러스터의 Prometheus 사이드카(NodePort로 노출된 주소)와 mgmt 내부 Store Gateway를 등록합니다.
  stores:
    - 172.21.0.4:31000   # biz1 클러스터의 노드 IP (예: biz1-control-plane)
    - 172.21.0.6:31000   # biz1 클러스터의 다른 노드 (또는 biz1에서 단일 주소만 사용)
    - 172.21.0.9:31000   # biz2 클러스터의 노드 IP (예: biz2-control-plane; 실제 IP 확인)
    - 172.21.0.10:31000  # biz2 클러스터의 다른 노드 (필요 시 단일 주소만 사용)
    - thanos-storegateway.monitoring.svc.cluster.local:10901  # mgmt 클러스터 내부 Store Gateway
  replicaCount: 2
  service:
    type: NodePort
    nodePorts:
      grpc: 30901
      http: 30902
  replicaLabel: prometheus_replica  # replicaLabel 설정으로 각 사이드카의 레이블을 구분

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
※ `<minio-cluster-IP>`는 minio 클러스터의 외부 IP로 교체합니다 (예: 172.18.0.10).

배포:
```bash
helm install thanos bitnami/thanos --version 15.13.0 -f values-thanos.yaml -n monitoring --create-namespace
```

---

### 3.5. Grafana 데이터 소스 수정 (biz 클러스터)

biz 클러스터의 Grafana에서는 Thanos 데이터 소스 URL을 mgmt 클러스터의 Thanos Query 외부 접근 주소로 수정합니다.  
예를 들어, mgmt 클러스터의 Thanos Query가 NodePort 9091로 노출되어 있다면:

```yaml
additionalDataSources:
  - name: Thanos
    type: prometheus
    access: proxy
    url: http://<mgmt-query-IP>:9091
    isDefault: false
    editable: true
```
여기서 `<mgmt-query-IP>`는 mgmt 클러스터의 Thanos Query가 노출된 IP (예: mgmt-control-plane의 IP)를 사용합니다.

mgmt 클러스터의 Thanos Query 서비스도 NodePort 또는 Ingress 방식으로 외부에 노출되어 있어야 합니다.

---

## 4. 네트워크 연결 및 테스트

### 4.1. mgmt 클러스터에서 biz 클러스터 NodePort 엔드포인트 테스트
mgmt 클러스터에서 임시 Pod를 생성하여 biz 클러스터의 Prometheus 사이드카(NodePort 31000)에 접근이 가능한지 확인합니다.
```bash
kubectl config use-context kind-mgmt
kubectl run -it --rm busybox --image=busybox --restart=Never -- /bin/sh
```
Pod 내부에서 다음 명령 실행:
```sh
wget -qO- http://172.21.0.4:31000/metrics
wget -qO- http://172.21.0.6:31000/metrics
wget -qO- http://172.21.0.9:31000/metrics
wget -qO- http://172.21.0.10:31000/metrics
```
정상 응답이 확인되면 네트워크 연결이 제대로 된 것입니다.

### 4.2. mgmt 클러스터 Thanos Query UI 확인
mgmt 클러스터의 Thanos Query UI (port-forward 또는 Ingress)를 통해 접속하고, "Stores" 탭에서 biz1, biz2의 사이드카와 mgmt 내부 Store Gateway가 올바르게 등록되었는지 확인합니다.

---

## 5. 최종 검증

1. **MinIO 클러스터**:
    - MinIO 서비스가 NodePort(32000)로 외부에 노출되고, minio-key.yaml의 endpoint가 올바르게 설정되어 있는지 확인합니다.
2. **biz 클러스터 (biz1, biz2)**:
    - Prometheus 사이드카가 NodePort(31000)로 외부에 노출되고, 각 클러스터의 externalLabels가 올바르게 적용되어 있는지 확인합니다.
3. **mgmt 클러스터**:
    - Thanos Query가 biz 클러스터의 사이드카 엔드포인트(NodePort 주소)와 mgmt 내부 Store Gateway를 올바르게 인식하는지, replicaLabel 설정(`prometheus_replica`) 덕분에 중복 경고 없이 통합 조회되는지 확인합니다.
4. **Grafana**:
    - 각 biz 클러스터의 Grafana 데이터 소스가 mgmt 클러스터의 Thanos Query 외부 접근 주소를 사용하도록 설정되어 있는지 확인합니다.

---

## 7. 결론

이 가이드를 따라 4개의 Kind 클러스터(mgmt, biz1, biz2, minio)를 구성하면,
- **minio 클러스터**는 독립적인 외부 스토리지로서 NodePort(32000)를 통해 접근 가능하며,
- **biz1 및 biz2 클러스터**는 Prometheus와 Thanos 사이드카를 NodePort(31000)로 외부에 노출하고, 각각 고유한 레이블로 구분되어,
- **mgmt 클러스터**의 Thanos Query는 biz 클러스터의 사이드카와 mgmt 내부의 Store Gateway를 통합하여 여러 클러스터의 데이터를 효율적으로 조회할 수 있습니다.
