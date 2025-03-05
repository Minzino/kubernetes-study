# 단일 클러스터 Thanos 환경 구축 가이드

- **Ingress‑NGINX** (Helm으로 설치, 웹훅 비활성화 및 잔여 클러스터 스코프 리소스 삭제 포함)
- **MinIO** (Thanos 외부 스토리지 역할, standalone 모드)
- **kube‑prometheus‑stack** (프로메테우스 HA, Grafana, Thanos 사이드카 포함)
- **Thanos 컴포넌트** (Query, Store Gateway, Compactor 등)
- **Grafana 데이터 소스** 자동 구성 (Thanos 데이터 소스 URL에 포트 9090 명시)

> 주의:
>
> - Helm 설치 시 `-version` 옵션은 필요에 따라 특정 버전을 명시할 수 있습니다.
> - 최신 버전을 사용하려면 버전 옵션을 생략하세요.
> - "latest"라는 버전 태그는 Helm 차트에서는 지원되지 않습니다.

---

## 1. 전제 조건

- **환경:** MacBook (M2/W2), Docker 기반 Kind 클러스터
- **필수 도구:** Docker, Kind, kubectl, Helm
- 터미널에서 `kubectl` 명령어 실행 권한

---

## 2. Kind 클러스터 생성

아래 내용으로 `kind-config.yaml` 파일을 생성합니다.

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    image: kindest/node:v1.29.7
  - role: control-plane
    image: kindest/node:v1.29.7
  - role: worker
    image: kindest/node:v1.29.7
  - role: worker
    image: kindest/node:v1.29.7

```

---

클러스터 생성:

```bash
kind create cluster --config kind-config.yaml
```

---

## 3. Ingress‑NGINX 컨트롤러 설치

### 3.1. 기존 리소스 삭제

이전에 생성된 Ingress‑NGINX 관련 클러스터 스코프 리소스가 있다면 삭제합니다:

```bash
kubectl delete namespace ingress-nginx
kubectl delete clusterrolebinding ingress-nginx
kubectl delete clusterrole ingress-nginx
kubectl delete ingressclass nginx
```

### 3.2. Helm을 통한 설치 (Admission Webhook 비활성화)

```bash
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update
helm install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx --create-namespace \
  --set controller.admissionWebhooks.enabled=false
```

### 3.3. 상태 확인

```bash
kubectl get pods -n ingress-nginx
```

모든 Ingress‑NGINX 관련 Pod가 Running 상태여야 합니다.

---

## 4. MinIO 배포

### 4.1. Helm 리포지토리 추가 및 업데이트

```bash
helm repo add minio https://charts.bitnami.com/bitnami
helm repo update
```

### 4.2. `values-minio.yaml` 파일 생성

```yaml
mode: standalone

auth:
  rootUser: admin
  rootPassword: "admin1234"

replicaCount: 1

ingress:
  enabled: true
  hostname: minio.local
  annotations:
    kubernetes.io/ingress.class: "nginx"
  paths:
    - path: /
      pathType: Prefix
      backend:
        service:
          name: minio
          port:
            number: 9000
    - path: /minio/v2/metrics/cluster
      pathType: Prefix
      backend:
        service:
          name: minio
          port:
            number: 9000

persistence:
  storageClass: "standard"
  size: 10Gi

extraEnvVars:
  - name: MINIO_PROMETHEUS_URL
    value: "http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090"
  - name: MINIO_PROMETHEUS_JOB_ID
    value: "minio-metrics"
```

### 4.3. 네임스페이스 생성 및 배포

```bash
kubectl create ns minio
helm install minio minio/minio -f values-minio.yaml -n minio

```

### 4.4. **Thanos용 버킷 생성**

Thanos 설정에서는 MinIO 내에 `thanos` 버킷을 사용합니다.

- Port-forward 후 [http://localhost:9000](http://localhost:9000/)에 접속하여 로그인(사용자: `admin`, 비밀번호: `admin1234`) 후 **thanos** 버킷을 수동으로 생성합니다.

---

## 5. MinIO Secret 생성 (Thanos용 S3 설정)

1. **`minio-key.yaml` 파일 생성**

    ```yaml
    # minio-key.yaml
    type: s3
    config:
      bucket: thanos
      endpoint: minio.minio.svc.cluster.local:9000
      access_key: admin
      secret_key: admin1234
      insecure: true
      signature_version2: false
    ```

2. **Secret 생성**

    ```bash
    kubectl create ns monitoring
    kubectl create secret generic thanos-minio-secret -n monitoring --from-file=minio-key.yaml
    ```


---

## 6. kube‑prometheus‑stack 배포 (프로메테우스 HA + Thanos 사이드카)

### 6.1. Helm 리포지토리 추가 및 업데이트

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
```

### 6.2. `values-kube-prometheus-stack.yaml` 파일 생성

```yaml
alertmanager:
  enabled: true

grafana:
  defaultDashboardsTimezone: Asia/Seoul
  adminPassword: admin1234
  ingress:
    enabled: true
    ingressClassName: "nginx"
    hosts:
      - grafana.local
    paths:
      - /
  additionalDataSources:
    - name: Thanos
      type: prometheus
      access: proxy
      url: http://thanos-query.monitoring.svc.cluster.local:9090
      isDefault: false
      editable: true

prometheus:
  thanosService:
    enabled: true
  ingress:
    enabled: true
    ingressClassName: "nginx"
    hosts:
      - prometheus.local
    paths:
      - /
  prometheusSpec:
    replicas: 1       # 로컬 테스트용으로 replica 수를 1로 줄임
    retention: 5d
    retentionSize: "10GiB"
    scrapeInterval: "15s"
#    externalLabels:
#      cluster: dev
    extraFlags:
      - --storage.tsdb.min-block-duration=2h
      - --storage.tsdb.max-block-duration=2h
    thanos:
      image: "quay.io/thanos/thanos:v0.24.0"
      objectStorageConfig:
        existingSecret:
          name: thanos-minio-secret
          key: minio-key.yaml
      version: v0.24.0
#    service:
#      extraPorts:
#        - name: sidecar-grpc
#          port: 10901
#          targetPort: 10901
#          protocol: TCP
#    storageSpec:
#      volumeClaimTemplate:
#        spec:
#          storageClassName: standard
#          accessModes: ["ReadWriteOnce"]
#          resources:
#            requests:
#              storage: 10Gi
    additionalScrapeConfigs:
      - job_name: 'minio-metrics'
        metrics_path: /minio/v2/metrics/cluster
        static_configs:
          - targets: ['minio.minio.svc.cluster.local:9000']
  thanosServiceMonitor:
    enabled: true

```

### 6.3. 배포

```bash
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  -f values-kube-prometheus-stack.yaml -n monitoring
```

> 참고: 버전 옵션을 생략하면 리포지토리의 최신 안정 버전을 사용합니다.
>
>
> 만약 특정 버전을 사용해야 한다면 `--version <버전번호>` 옵션을 추가하세요.
>

> 예시:
>
> - `-version 45.7.1`

---

## 7. Thanos 컴포넌트 배포

### 7.1. Helm 리포지토리 추가 및 업데이트

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update
```

### 7.2. `values-thanos.yaml` 파일 생성

```yaml
objstoreConfig: |-
  type: s3
  config:
    bucket: thanos
    endpoint: minio.minio.svc.cluster.local:9000
    access_key: admin
    secret_key: admin1234
    insecure: true
    signature_version2: false

querier:
  stores:
    - kube-prometheus-stack-thanos-discovery.monitoring.svc.cluster.local:10901
    - thanos-storegateway.monitoring.svc.cluster.local:10901
  replicaCount: 2
#  extraFlags:
#    - --store=0.0.0.0:10901
  ingress:
    enabled: true
    hostname: thanos.local
    ingressClassName: "nginx"
    path: /

bucketweb:
  enabled: true
compactor:
  enabled: true
storegateway:
  enabled: true

# Enable Thanos Ruler to centrally manage alerting/recording rules.
ruler:
  enabled: true
  alertmanagers:
    - http://alertmanager.monitoring.svc.cluster.local:9093
  config: |-
    groups:
    - name: default
      rules: []
  ingress:
    enabled: true
    hostname: thanos-ruler.local
    ingressClassName: "nginx"
    path: /

```

### 7.3. 배포

```bash
helm install thanos bitnami/thanos --version 12.3.2 -f values-thanos.yaml -n monitoring
```

> 참고: 마찬가지로, 특정 버전을 사용하려면 --version <버전번호> 옵션을 추가합니다.
>
>
> 예시: `--version 12.3.2`
>

---

## 9. kubectl port‑forward를 통한 서비스 접근 및 테스트

Docker 기반 Kind 환경에서는 /etc/hosts 대신 port‑forward 명령어를 사용합니다.

### 9.1. MinIO 접속

```bash
kubectl port-forward svc/minio 9001:9001 -n minio
```

- **테스트:** 브라우저에서 [http://localhost:9000](http://localhost:9000/)에 접속
- **확인:** 로그인 (사용자: `admin`, 비밀번호: `admin1234`) 후, **thanos** 버킷 내에 Thanos가 업로드한 블록 파일(객체)이 있는지 확인
- 하루 지나니 버킷에 로그가 쌓인 것을 확인할 수

  ![image.png](attachment:2accb84e-cc7d-46d5-82d5-34ff3f63f026:image.png)


### 9.2. Grafana 접속

```bash
kubectl port-forward svc/kube-prometheus-stack-grafana 3000:80 -n monitoring
```

- **테스트:** 브라우저에서 [http://localhost:3000](http://localhost:3000/)에 접속
- **확인:** 로그인 후, 데이터 소스 및 대시보드가 정상 표시되며, 프로비저닝된 “Thanos” 데이터 소스가 올바른 URL (포트 9090 포함)로 등록되어 있는지 확인

### 9.3. Prometheus 접속

```bash
kubectl port-forward svc/kube-prometheus-stack-prometheus 9090:80 -n monitoring
```

- **테스트:** 브라우저에서 [http://localhost:9090](http://localhost:9090/)에 접속
- **확인:** “Status → Targets”에서 Thanos 사이드카를 포함한 타겟들이 UP 상태인지, `up` 쿼리 결과 확인

### 9.4. Thanos Query 접속

```bash
kubectl port-forward svc/thanos-query 9091:80 -n monitoring

```

- **테스트:** 브라우저에서 [http://localhost:9091](http://localhost:9091/)에 접속
- **확인:** Thanos Query UI에서 여러 Prometheus 인스턴스의 메트릭이 통합 조회되는지 확인

### 9.5. 커맨드라인 HTTP 응답 확인

```bash
curl -I http://localhost:9000    # MinIO
curl -I http://localhost:3000    # Grafana
curl -I http://localhost:9090    # Prometheus
curl -I http://localhost:9091    # Thanos Query

```

각 응답에서 HTTP 200 코드가 반환되면 정상입니다.

---

## 10. Thanos → MinIO 연동 확인

Thanos가 MinIO에 데이터를 업로드하는지 확인하는 방법:

### 10.1. Thanos 로그 확인

- Thanos 사이드카와 Store Gateway 로그에서 “uploading block” 또는 “successfully uploaded” 메시지를 확인합니다.

    ```bash
    kubectl logs <thanos-sidecar-pod> -n monitoring
    kubectl logs <thanos-storegateway-pod> -n monitoring
    ```

- 로그에 MinIO 엔드포인트 (`minio.minio.svc.cluster.local:9000`) 관련 메시지가 보이면 정상입니다.

### 10.2. MinIO UI 확인

- MinIO 웹 UI에 로그인 후, **thanos** 버킷 내에 Thanos가 업로드한 블록 파일(객체)이 생성되어 있는지 확인합니다.

### 10.3. Thanos Query 데이터 확인

- Thanos Query UI에서 기본 쿼리 (`up` 등)를 실행하여 여러 Prometheus 인스턴스의 메트릭이 통합 조회되면, MinIO 연동이 성공한 것입니다.

---

## 11. 추가 점검 사항

- **리소스 상태 확인:**

    ```bash
    kubectl get pods -n ingress-nginx
    kubectl get pods -n minio
    kubectl get pods -n monitoring
    ```

- **Pod 상세 정보 및 이벤트 확인:**

    ```bash
    kubectl describe pod <pod-name> -n <namespace>
    ```

- **Ingress‑NGINX 관련 문제:**
  Ingress‑NGINX 컨트롤러가 Pending 상태이거나 웹훅 오류가 발생하면 노드 리소스, taint, 스케줄링 이슈를 점검하고 필요 시 위의 삭제 후 재설치(웹훅 비활성화)를 진행합니다.

---

## 12. 마무리

이 가이드를 통해 Docker 기반 Kind 클러스터에서 Ingress‑NGINX(클러스터 스코프 리소스 삭제 및 재설치), MinIO(및 **thanos** 버킷 생성), kube‑prometheus‑stack, Thanos 컴포넌트를 설치하여 프로메테우스 HA 환경을 구축할 수 있습니다.

특히 Grafana의 Thanos 데이터 소스 URL에 포트 **9090**을 명시하여 “connection refused” 오류를 해결하였으며, Thanos가 MinIO에 데이터를 업로드하는지 로그, MinIO UI 및 Thanos Query를 통해 확인할 수 있습니다.

> 버전 옵션 사용 주의:
>
>
> Helm 설치 시 버전 옵션은 필요 시 `--version <버전번호>`로 명시합니다.
>
> 현재 가이드에서는 kube‑prometheus‑stack과 Thanos의 버전을 명시하지 않고 최신 안정 버전을 사용하며, 특정 버전 사용이 필요하면 해당 옵션을 추가하면 됩니다.
>