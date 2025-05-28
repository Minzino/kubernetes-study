import os
import subprocess
import time

# 설정
WORKER_NODE = {
    "hostname": "k8s-hardway-worker01",
    "ip": "192.168.89.21",
    "kubeconfig": "k8s-hardway-worker01.kubeconfig",
}
DOCKER_PACKAGE = "docker.io"
BINARIES = [
    "kubectl",
    "kube-proxy",
    "kubelet"
]
CNI_PLUGIN_URL = "https://github.com/containernetworking/plugins/releases/download/v1.6.2/cni-plugins-linux-amd64-v1.6.2.tgz"
INSTALL_DIR = "/usr/local/bin"
KUBE_DIR = "/etc/kubernetes"
CNI_DIR = "/opt/cni/bin"
CERTS_DIR = "/etc/kubernetes/ssl"
SOURCE_CERTS_DIR = "/home/ubuntu/hardway/certs"  # 원본 인증서 디렉토리
LOG_FILE = "/root/worker01_setup.log"


# 로그 작성 함수
def log_message(message):
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    with open(LOG_FILE, "a", encoding="utf-8") as log:
        log.write(f"{timestamp} - {message}\n")
    print(message)


# 명령 실행 함수
def run_command(command):
    try:
        result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        log_message(result.stdout.decode().strip())
    except subprocess.CalledProcessError as e:
        log_message(f"❌ 명령 실행 실패: {command}\n{e.stderr.decode().strip()}")
        raise


# 디렉토리 확인 및 생성 함수
def ensure_directory(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)
        log_message(f"✅ 디렉토리 생성 완료: {directory}")
    else:
        log_message(f"⚠️ 디렉토리가 이미 존재합니다: {directory}")


# 인증서 및 kubeconfig 복사 함수
def copy_certificates_and_configs():
    log_message("🔄 인증서 및 kubeconfig 복사 중...")
    ensure_directory(CERTS_DIR)

    required_files = [
        "ca.crt",
        f"{WORKER_NODE['hostname']}.crt",
        f"{WORKER_NODE['hostname']}.key",
        "kube-proxy.kubeconfig"
    ]

    for file in required_files:
        src_path = os.path.join(SOURCE_CERTS_DIR, file)
        dest_path = os.path.join(CERTS_DIR, file if "kube-proxy.kubeconfig" not in file else f"{KUBE_DIR}/{file}")

        if os.path.exists(dest_path):
            log_message(f"⚠️ 파일이 이미 존재합니다: {dest_path}")
        elif os.path.exists(src_path):
            run_command(f"cp {src_path} {dest_path}")
            log_message(f"✅ 파일 복사 완료: {file}")
        else:
            log_message(f"❌ 필수 파일 누락: {file}")
            raise FileNotFoundError(f"File {src_path} does not exist")


# Docker 설치 함수
def install_docker():
    log_message("🔄 Docker 설치 중...")
    run_command("apt-get update")
    if subprocess.call(["dpkg", "-s", DOCKER_PACKAGE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
        log_message("✅ Docker가 이미 설치되어 있습니다.")
    else:
        run_command(f"apt-get install -y {DOCKER_PACKAGE}")
        log_message("✅ Docker 설치 완료")
    run_command("swapoff -a")


# Docker 서비스 설정 함수
def setup_docker_service():
    log_message("🔄 Docker 서비스 설정 중...")
    run_command("systemctl daemon-reload")
    run_command("systemctl enable docker")
    run_command("systemctl restart docker")
    log_message("✅ Docker 서비스 설정 완료")


# 바이너리 설치 함수
def install_binaries():
    log_message("🔄 Kubernetes 바이너리 설치 중...")
    ensure_directory(INSTALL_DIR)

    for binary in BINARIES:
        binary_path = os.path.join(INSTALL_DIR, binary)
        if os.path.exists(binary_path):
            log_message(f"✅ {binary} 이미 설치되어 있습니다: {binary_path}")
            continue

        run_command(
            f"wget -q -P /tmp https://storage.googleapis.com/kubernetes-release/release/v1.29.7/bin/linux/amd64/{binary}")
        run_command(f"chmod +x /tmp/{binary}")
        run_command(f"mv /tmp/{binary} {INSTALL_DIR}/")
        log_message(f"✅ {binary} 설치 완료: {binary_path}")


# CNI 플러그인 설치 함수
def install_cni_plugins():
    log_message("🔄 CNI 플러그인 설치 중...")
    ensure_directory(CNI_DIR)
    cni_tarball = "/tmp/cni-plugins.tgz"

    if not os.path.exists(cni_tarball):
        run_command(f"wget -q -O {cni_tarball} {CNI_PLUGIN_URL}")
        log_message("✅ CNI 플러그인 다운로드 완료")

    run_command(f"tar -xzvf {cni_tarball} -C {CNI_DIR}")
    log_message("✅ CNI 플러그인 설치 완료")


# kube-proxy 설정 파일 생성 함수
def create_kube_proxy_config():
    log_message("🔄 kube-proxy 설정 파일 생성 중...")
    kube_proxy_config = f"""kind: KubeProxyConfiguration
apiVersion: kubeproxy.config.k8s.io/v1alpha1
clientConnection:
  kubeconfig: "{KUBE_DIR}/kube-proxy.kubeconfig"
mode: "iptables"
clusterCIDR: "10.240.0.0/13"
"""
    with open(f"{KUBE_DIR}/kube-proxy-config.yaml", "w") as f:
        f.write(kube_proxy_config)
    log_message("✅ kube-proxy 설정 파일 생성 완료")


# kubelet 설정 파일 생성 함수
def create_kubelet_config():
    log_message("🔄 kubelet 설정 파일 생성 중...")
    kubelet_config = f"""kind: KubeletConfiguration
apiVersion: kubelet.config.k8s.io/v1beta1
authentication:
  anonymous:
    enabled: false
  webhook:
    enabled: true
  x509:
    clientCAFile: "{CERTS_DIR}/ca.crt"
authorization:
  mode: Webhook
clusterDomain: "cluster.local"
clusterDNS:
- 10.231.0.10
resolvConf: "/run/systemd/resolve/resolv.conf"
runtimeRequestTimeout: "15m"
"""
    with open(f"{KUBE_DIR}/kubelet-config.yaml", "w") as f:
        f.write(kubelet_config)
    log_message("✅ kubelet 설정 파일 생성 완료")


# kubelet 서비스 파일 생성 함수
def create_kubelet_service():
    log_message("🔄 kubelet 서비스 파일 생성 중...")
    service_content = f"""[Unit]
Description=Kubernetes Kubelet
Documentation=https://github.com/kubernetes/kubernetes
After=docker.service
Requires=docker.service

[Service]
ExecStart={INSTALL_DIR}/kubelet \\
  --config={KUBE_DIR}/kubelet-config.yaml \\
  --kubeconfig={KUBE_DIR}/{WORKER_NODE['kubeconfig']} \\
  --tls-cert-file={CERTS_DIR}/{WORKER_NODE['hostname']}.crt \\
  --tls-private-key-file={CERTS_DIR}/{WORKER_NODE['hostname']}.key \\
  --register-node=true --v=2
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
    with open("/etc/systemd/system/kubelet.service", "w") as f:
        f.write(service_content)
    log_message("✅ kubelet 서비스 파일 생성 완료")


# kube-proxy 서비스 파일 생성 함수
def create_kube_proxy_service():
    log_message("🔄 kube-proxy 서비스 파일 생성 중...")
    service_content = f"""[Unit]
Description=Kubernetes Kube Proxy
Documentation=https://github.com/kubernetes/kubernetes

[Service]
ExecStart={INSTALL_DIR}/kube-proxy \\
  --config={KUBE_DIR}/kube-proxy-config.yaml
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
    with open("/etc/systemd/system/kube-proxy.service", "w") as f:
        f.write(service_content)
    log_message("✅ kube-proxy 서비스 파일 생성 완료")


# 서비스 시작 함수
def start_services():
    log_message("🔄 서비스 시작 중...")
    run_command("systemctl daemon-reload")
    run_command("systemctl enable kubelet kube-proxy")
    run_command("systemctl start kubelet kube-proxy")
    log_message("✅ 서비스 시작 완료")


# 메인 함수
def main():
    log_message("=== Worker Node 1 설정 시작 ===")
    install_docker()
    setup_docker_service()
    install_binaries()
    install_cni_plugins()
    ensure_directory(KUBE_DIR)
    copy_certificates_and_configs()
    create_kube_proxy_config()
    create_kubelet_config()
    create_kubelet_service()
    create_kube_proxy_service()
    start_services()
    log_message("=== Worker Node 1 설정 완료 ===")


if __name__ == "__main__":
    main()
