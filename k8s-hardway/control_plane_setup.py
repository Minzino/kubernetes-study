import os
import subprocess
import time

# 설정
KUBE_VERSION = "v1.29.7"
BINARIES = [
    "kubectl",
    "kube-apiserver",
    "kube-controller-manager",
    "kube-scheduler"
]
DOWNLOAD_URL = f"https://storage.googleapis.com/kubernetes-release/release/{KUBE_VERSION}/bin/linux/amd64/"
DOWNLOAD_DIR = "/home/ubuntu/hardway/certs"
INSTALL_DIR = "/usr/local/bin"
CERT_DIR = "/home/ubuntu/hardway/certs"
KUBE_CONFIG_DIR = "/home/ubuntu/hardway/certs"
LOG_FILE = "/home/ubuntu/hardway/k8s_setup.log"
NETWORK_INTERFACE = "ens33"
DATA_DIR = "/etc/kubernetes/ssl"
KUBECONFIG_PATH = "/etc/kubernetes/admin.kubeconfig"
VIP = "192.168.89.150"

# 로그와 출력 함수
def log_and_print(message):
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    formatted_message = f"{timestamp} - {message}"
    with open(LOG_FILE, "a", encoding="utf-8") as log:
        log.write(formatted_message + "\n")
    print(formatted_message)

# 명령 실행 함수
def run_command(command):
    try:
        result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        log_and_print(result.stdout.decode().strip())
    except subprocess.CalledProcessError as e:
        log_and_print(f"❌ 명령 실행 실패: {command}\n{e.stderr.decode().strip()}")
        raise

# 바이너리 다운로드 및 설치
def download_and_install_binaries():
    log_and_print("🔄 Kubernetes 바이너리 다운로드 및 설치 중...")
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    for binary in BINARIES:
        binary_path = os.path.join(DOWNLOAD_DIR, binary)
        install_path = os.path.join(INSTALL_DIR, binary)

        if os.path.exists(install_path):
            log_and_print(f"✅ {binary} 이미 설치됨: {install_path}")
            continue

        if not os.path.exists(binary_path):
            run_command(f"wget -q -O {binary_path} {DOWNLOAD_URL}{binary}")
            log_and_print(f"✅ {binary} 다운로드 완료: {binary_path}")
        else:
            log_and_print(f"⚠️ {binary} 이미 다운로드됨: {binary_path}")

        run_command(f"chmod +x {binary_path}")
        run_command(f"sudo mv {binary_path} {INSTALL_DIR}/")
        log_and_print(f"✅ {binary} 설치 완료: {install_path}")

# 인증서 및 kubeconfig 파일 복사, 공개키 생성 추가
def setup_certificates_and_kubeconfigs():
    log_and_print("🔄 인증서 및 kubeconfig 파일 설정 중...")
    os.makedirs(DATA_DIR, exist_ok=True)

    cert_files = [
        "ca.crt", "ca.key", "kube-apiserver.crt", "kube-apiserver.key",
        "service-account.key", "service-account.crt"
    ]

    for cert in cert_files:
        src = os.path.join(CERT_DIR, cert)
        dest = f"/etc/kubernetes/ssl/{cert}"
        if os.path.exists(dest):
            log_and_print(f"⚠️ {dest} 파일이 이미 존재합니다.")
        else:
            run_command(f"sudo mkdir -p /etc/kubernetes/ssl && sudo cp {src} {dest}")
            log_and_print(f"✅ {cert} 복사 완료: {dest}")

    # 공개키 생성
    service_account_key = "/etc/kubernetes/ssl/service-account.key"
    service_account_pub = "/etc/kubernetes/ssl/service-account.pub"
    if not os.path.exists(service_account_pub):
        run_command(f"openssl rsa -in {service_account_key} -pubout -out {service_account_pub}")
        log_and_print(f"✅ 공개키 생성 완료: {service_account_pub}")
    else:
        log_and_print(f"⚠️ {service_account_pub} 파일이 이미 존재합니다.")

    kubeconfig_files = [
        "admin.kubeconfig",
        "kube-controller-manager.kubeconfig",
        "kube-scheduler.kubeconfig"
    ]

    for kubeconfig in kubeconfig_files:
        src = os.path.join(KUBE_CONFIG_DIR, kubeconfig)
        dest = f"/etc/kubernetes/{kubeconfig}"
        if os.path.exists(dest):
            log_and_print(f"⚠️ {dest} 파일이 이미 존재합니다.")
        else:
            run_command(f"sudo cp {src} {dest}")
            log_and_print(f"✅ {kubeconfig} 복사 완료: {dest}")

# systemd 서비스 파일 생성
def create_systemd_services():
    log_and_print("🔄 systemd 서비스 파일 생성 중...")

    services = {
        "kube-apiserver": f"""[Unit]
Description=Kubernetes API Server
Documentation=https://github.com/kubernetes/kubernetes

[Service]
ExecStart=/usr/local/bin/kube-apiserver \
  --service-account-issuer=https://kubernetes.default.svc.cluster.local \
  --service-account-signing-key-file=/etc/kubernetes/ssl/service-account.key \
  --service-account-key-file=/etc/kubernetes/ssl/service-account.pub \
  --advertise-address={VIP} --allow-privileged=true --apiserver-count=3 \
  --service-cluster-ip-range=10.231.0.0/18 --service-node-port-range=30000-32767 \
  --authorization-mode=Node,RBAC --bind-address=0.0.0.0 --v=2 \
  --client-ca-file=/etc/kubernetes/ssl/ca.crt --enable-admission-plugins=NodeRestriction,ServiceAccount \
  --enable-bootstrap-token-auth=true \
  --etcd-cafile=/etc/kubernetes/ssl/ca.crt --etcd-certfile=/etc/ssl/etcd/ssl/etcd-server.crt --etcd-keyfile=/etc/ssl/etcd/ssl/etcd-server.key \
  --etcd-servers=https://192.168.89.11:2379,https://192.168.89.12:2379,https://192.168.89.13:2379 \
  --event-ttl=1h \
  --kubelet-client-certificate=/etc/kubernetes/ssl/kube-apiserver.crt \
  --kubelet-client-key=/etc/kubernetes/ssl/kube-apiserver.key \
  --tls-cert-file=/etc/kubernetes/ssl/kube-apiserver.crt --tls-private-key-file=/etc/kubernetes/ssl/kube-apiserver.key
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
""",
        "kube-controller-manager": f"""[Unit]
Description=Kubernetes Controller Manager
Documentation=https://github.com/kubernetes/kubernetes

[Service]
ExecStart=/usr/local/bin/kube-controller-manager \
  --bind-address=0.0.0.0 --cluster-cidr=10.240.0.0/13 --allocate-node-cidrs=true \
  --cluster-name=minje-k8s-hardway \
  --cluster-signing-cert-file=/etc/kubernetes/ssl/ca.crt \
  --cluster-signing-key-file=/etc/kubernetes/ssl/ca.key \
  --kubeconfig=/etc/kubernetes/kube-controller-manager.kubeconfig \
  --leader-elect=true --root-ca-file=/etc/kubernetes/ssl/ca.crt \
  --service-account-private-key-file=/etc/kubernetes/ssl/service-account.key \
  --service-cluster-ip-range=10.231.0.0/18 --use-service-account-credentials=true --v=2
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
""",
        "kube-scheduler": f"""[Unit]
Description=Kubernetes Scheduler
Documentation=https://github.com/kubernetes/kubernetes

[Service]
ExecStart=/usr/local/bin/kube-scheduler \
  --kubeconfig=/etc/kubernetes/kube-scheduler.kubeconfig \
  --bind-address=127.0.0.1 \
  --leader-elect=true --v=2
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
    }

    for service_name, service_content in services.items():
        service_path = f"/etc/systemd/system/{service_name}.service"
        with open(service_path, "w") as service_file:
            service_file.write(service_content)
        log_and_print(f"✅ {service_name} 서비스 파일 생성 완료: {service_path}")

# 서비스 시작
def start_services():
    log_and_print("🔄 서비스 시작 중...")
    run_command("systemctl daemon-reload")
    run_command("systemctl enable kube-apiserver kube-controller-manager kube-scheduler")
    run_command("systemctl start kube-apiserver kube-controller-manager kube-scheduler")
    log_and_print("✅ 모든 서비스 시작 완료")

# 메인 함수
def main():
    log_and_print("=== Kubernetes Control Plane 설정 시작 ===")
    download_and_install_binaries()
    setup_certificates_and_kubeconfigs()
    create_systemd_services()
    start_services()
    log_and_print("=== Kubernetes Control Plane 설정 완료 ===")

if __name__ == "__main__":
    main()
