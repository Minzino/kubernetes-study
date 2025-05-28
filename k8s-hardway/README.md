## Kubernetes Hardway 클러스터 구축 자동화 스크립트

> **주의:**  
> 아직 IP를 직접 입력해서 세팅하도록 개발이 되어있지 않습니다.  
> 해당 스크립트를 사용하려면 소스코드의 IP를 사용하시는 VM의 IP와 동일하게 세팅 후 사용바랍니다.  
> 추가로 SSH 사용 시 `root` 계정과 **비밀번호 인증**을 사용하도록 되어 있습니다.

---

### 📚 개요 (Overview)

이 스크립트는 **Kubernetes 클러스터를 HardWay 방식**으로 구축하기 위한 자동화 스크립트 모음입니다.  
Bastion 서버를 중심으로 **인증서 생성, 전송, 노드 초기화 및 네트워크 구성** 작업을 효율적으로 수행하도록 설계되었습니다.  
Python 기반의 자동화 스크립트를 통해 **ETCD, Control Plane, Worker Node** 설정을 간소화하고, 네트워크 플러그인으로 **Cilium**을 활용합니다.  

---

### 🛠 주요 기능 (Key Features)

- **자동화된 배포:** `auto_main.py`를 실행하면 모든 작업이 순차적으로 실행됨.
- **Bastion 서버 중심 관리:** Bastion 서버에서 인증서 생성 및 관리, 노드 설정.
- **병렬 작업 지원:** Master 및 Worker 노드 설정을 병렬로 처리하여 배포 속도 향상.
- **Cilium 네트워크 플러그인 설치:** Kubernetes 네트워킹을 위해 Cilium을 자동으로 구성.
- **TLS Bootstrapping 및 보안 강화:** RBAC 및 TLS 보안 구성 제공.

---

### 📋 VM 초기 세팅 (Initial VM Setup)

Kubernetes 클러스터 배포를 위한 기본 VM 설정을 아래와 같이 진행합니다.

---

### 1. Root 계정 활성화 및 SSH 설정

```bash
# Root 계정 패스워드 설정
sudo passwd root

# SSH 설정 파일 수정
sudo vi /etc/ssh/sshd_config
```

다음 내용을 추가 또는 수정합니다.

```bash
PermitRootLogin yes
PasswordAuthentication yes
```

설정을 적용하기 위해 SSH 서비스 재시작:

```bash
sudo systemctl restart sshd
```

---

### 2. Bastion 서버 필수 패키지 설치

Bastion 서버에서는 기본적인 유틸리티와 Python 패키지를 설치해야 합니다.

```bash
apt update -y;\
apt upgrade -y;\
apt install net-tools htop vim openssl ipset python3-pip -y;\
pip install -r requirements.txt
```

---

### 3. /etc/hosts 파일 설정

클러스터 내 각 노드가 서로를 인식할 수 있도록 `/etc/hosts` 파일에 다음을 추가합니다.  
(**사용자의 IP 환경에 맞게 수정 필요**)

```bash
cat << EOF >> /etc/hosts
127.0.0.1 localhost
192.168.89.11 k8s-hardway-master01
192.168.89.12 k8s-hardway-master02
192.168.89.13 k8s-hardway-master03
192.168.89.21 k8s-hardway-worker01
192.168.89.22 k8s-hardway-worker02
192.168.89.23 k8s-hardway-worker03
EOF
```

---

### 🚀 설치 및 실행 방법 (Installation & Usage)

---

### 1. 프로젝트 다운로드 및 설정

```bash
# 리포지토리 클론
git clone https://github.com/Minzino/kubernetes-study.git
cd k8s-hardway

# Python 의존성 설치
pip install -r requirements.txt
```
 
---

### 2. Bastion 서버에서 자동 실행 (전체 배포)

모든 작업을 자동으로 수행하려면 `auto_main.py`를 실행합니다.  
스크립트 실행 시 **root 비밀번호**를 입력해야 합니다.

```bash
python3 auto_main.py
```

---

### 3. 수동 실행 (단계별 수행)

각 단계를 개별적으로 실행하려면 `main.py`를 실행 후 메뉴에서 선택합니다.  
스크립트 실행 시 **root 비밀번호**를 입력해야 합니다.

```bash
python3 main.py
```

#### 실행 가능한 작업 목록:
```plaintext
1. VIP 설정 (Pacemaker/Corosync)
2. 인증서 생성
3. 인증서 전송
4. ETCD 클러스터 구성
5. ETCD 상태 검증
6. Control Plane 설정
7. Worker Node 인증서 생성 및 전송
8. Main Worker 노드 설정
9. CNI 세팅 (Bastion Cilium)
10. TLS Bootstrapping 설정
11. Sub Worker Node 인증서 전송
12. Sub Worker Node 초기 세팅
13. 종료
```

---

### 📂 디렉토리 구조 (Directory Structure)

```plaintext
.
├── bizclsuter-deploy/               # 주요 스크립트 파일
│   ├── auto_main.py                 # 전체 배포 자동 실행 스크립트
│   ├── main.py                       # 수동 배포 스크립트
│   ├── pcs_setup.py                  # VIP 설정 (Pacemaker/Corosync)
│   ├── cert_create.py                 # 인증서 생성 스크립트
│   ├── cert_transfer.py               # 인증서 전송 스크립트
│   ├── etcd_setup.py                  # ETCD 클러스터 구성
│   ├── etcd_verify.py                  # ETCD 상태 검증
│   ├── control_plane_setup.py          # Control Plane 설정
│   ├── cert_create_worker.py           # Worker Node 인증서 생성 및 전송
│   ├── worker_node_setup.py            # Worker Node 초기 설정 (Main Worker)
│   ├── cni_setup.py                     # Cilium 네트워크 플러그인 설정
│   ├── tls_setup.py                     # TLS Bootstrapping 설정
│   ├── cert_sub_worker_node_transfer.py # 추가 Worker 인증서 전송
│   ├── sub_worker_node_setup.py         # 추가 Worker 노드 설정
│   ├── requirements.txt                 # Python 의존성 목록
│   ├── README.md                        # 프로젝트 설명 문서
└── .gitignore                           # Git 무시 파일 설정
```

---

### ⚠️ 주의 사항 (Precautions)

1. **IP 및 호스트 이름 설정:**  
   - 소스코드에서 사용되는 IP 주소를 환경에 맞게 변경해야 합니다.  
   - `/etc/hosts` 파일과 일치하는지 확인하십시오.

2. **Root 계정 사용:**  
   - 스크립트 실행 시 root 계정 사용이 필수입니다.  
   - 비밀번호 없이 SSH 접속을 위해 SSH 키를 설정하는 것이 권장됩니다.

3. **방화벽 설정:**  
   - 노드 간 원활한 통신을 위해 방화벽 설정을 확인하십시오.  
   - Kubernetes 포트(6443, 10250 등)가 열려 있어야 합니다.

