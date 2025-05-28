import os
import subprocess
import time

# 기본 설정
ETCD_VERSION = "v3.5.17"
ETCD_DOWNLOAD_URL = f"https://github.com/etcd-io/etcd/releases/download/{ETCD_VERSION}/etcd-{ETCD_VERSION}-linux-amd64.tar.gz"
DOWNLOAD_DIR = "/home/ubuntu/hardway/certs"
ETCD_BIN_DIR = "/usr/local/bin"
ETCD_SSL_DIR = "/etc/ssl/etcd/ssl"
ETCD_DATA_DIR = "/var/lib/etcd"
SYSTEMD_SERVICE_FILE = "/etc/systemd/system/etcd.service"
LOG_FILE = "/root/hardway/etcd_setup.log"

# 클러스터 설정
CLUSTER_NAME = "etcd-cluster-0"
MASTER_NODES = [
    {"name": "k8s-hardway-master01", "ip": "192.168.89.11"},
    {"name": "k8s-hardway-master02", "ip": "192.168.89.12"},
    {"name": "k8s-hardway-master03", "ip": "192.168.89.13"},
]

# 환경 변수
ETCD_ENV_VARS = {
    "ETCDCTL_API": "3",
    "ETCDCTL_CERT": f"{ETCD_SSL_DIR}/etcd-server.crt",
    "ETCDCTL_KEY": f"{ETCD_SSL_DIR}/etcd-server.key",
    "ETCDCTL_CACERT": f"{ETCD_SSL_DIR}/ca.crt",
}

# 로그 및 출력 함수
def log_and_print(message):
    # Ensure log directory exists
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    formatted_message = f"[{timestamp}] {message}"
    print(formatted_message)
    with open(LOG_FILE, "a", encoding="utf-8", errors="replace") as log:
        log.write(formatted_message + "\n")

# 명령 실행 함수
def run_command(command):
    try:
        result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        log_and_print(result.stdout.decode().strip())
    except subprocess.CalledProcessError as e:
        log_and_print(f"❌ 명령 실행 실패: {command}\n{e.stderr.decode().strip()}")
        raise

# 환경 변수 설정 및 영구 적용
def setup_environment_variables():
    log_and_print("🔄 환경 변수 설정 중...")
    bashrc_path = os.path.expanduser("~/.bashrc")

    for var, value in ETCD_ENV_VARS.items():
        os.environ[var] = value
        log_and_print(f"✅ 환경 변수 설정: {var}={value}")

        # .bashrc에 추가
        with open(bashrc_path, "r", encoding="utf-8", errors="replace") as bashrc:
            if f"export {var}=" in bashrc.read():
                log_and_print(f"⚠️ {var} 이미 설정됨")
                continue

        with open(bashrc_path, "a", encoding="utf-8", errors="replace") as bashrc:
            bashrc.write(f"export {var}={value}\n")
            log_and_print(f"✅ {var} 추가 완료")

    log_and_print("✅ 환경 변수 설정 및 영구 적용 완료")

# etcd 다운로드 및 설치
def install_etcd():
    log_and_print("🔄 etcd 다운로드 및 설치 중...")
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    etcd_tarball = os.path.join(DOWNLOAD_DIR, f"etcd-{ETCD_VERSION}-linux-amd64.tar.gz")
    if not os.path.exists(etcd_tarball):
        run_command(f"wget -q -O {etcd_tarball} {ETCD_DOWNLOAD_URL}")
        log_and_print(f"✅ etcd 다운로드 완료: {etcd_tarball}")
    else:
        log_and_print(f"✅ etcd 이미 다운로드됨: {etcd_tarball}")

    extracted_dir = os.path.join(DOWNLOAD_DIR, f"etcd-{ETCD_VERSION}-linux-amd64")
    if not os.path.exists(extracted_dir):
        run_command(f"tar -xvf {etcd_tarball} -C {DOWNLOAD_DIR}")
        run_command(f"mv {extracted_dir}/etcd* {ETCD_BIN_DIR}/")
        log_and_print("✅ etcd 설치 완료")
    else:
        log_and_print(f"⚠️ etcd 디렉토리 이미 존재: {extracted_dir}")

# 디렉토리 및 인증서 복사
def setup_directories_and_certs():
    log_and_print("🔄 디렉토리 및 인증서 설정 중...")
    os.makedirs(ETCD_SSL_DIR, exist_ok=True)
    os.makedirs(ETCD_DATA_DIR, exist_ok=True)
    run_command(f"chmod 700 {ETCD_DATA_DIR}")

    cert_files = ["ca.crt", "etcd-server.key", "etcd-server.crt"]
    for cert in cert_files:
        src = os.path.join(DOWNLOAD_DIR, cert)
        dest = os.path.join(ETCD_SSL_DIR, cert)
        if os.path.exists(dest):
            log_and_print(f"⚠️ 파일이 이미 존재합니다: {dest}")
        else:
            run_command(f"cp {src} {dest}")
            log_and_print(f"✅ {cert} 복사 완료")

# systemd 서비스 파일 생성
def create_systemd_service():
    log_and_print("🔄 systemd 서비스 파일 생성 중...")
    internal_ip = subprocess.getoutput(
        "ip addr show ens33 | grep -w 'inet' | awk '{print $2}' | cut -d/ -f1 | head -n 1").strip()
    hostname = subprocess.getoutput("hostname -s").strip()

    initial_cluster = ",".join([
        f"{node['name']}=https://{node['ip']}:2380" for node in MASTER_NODES
    ])

    service_content = f"""[Unit]
Description=etcd
Documentation=https://github.com/coreos

[Service]
ExecStart=/usr/local/bin/etcd \
  --name {hostname} \
  --cert-file={ETCD_SSL_DIR}/etcd-server.crt \
  --key-file={ETCD_SSL_DIR}/etcd-server.key \
  --peer-cert-file={ETCD_SSL_DIR}/etcd-server.crt \
  --peer-key-file={ETCD_SSL_DIR}/etcd-server.key \
  --trusted-ca-file={ETCD_SSL_DIR}/ca.crt \
  --peer-trusted-ca-file={ETCD_SSL_DIR}/ca.crt \
  --peer-client-cert-auth \
  --client-cert-auth \
  --initial-advertise-peer-urls https://{internal_ip}:2380 \
  --listen-peer-urls https://{internal_ip}:2380 \
  --listen-client-urls https://{internal_ip}:2379,https://127.0.0.1:2379 \
  --advertise-client-urls https://{internal_ip}:2379 \
  --initial-cluster-token {CLUSTER_NAME} \
  --initial-cluster-state new \
  --data-dir={ETCD_DATA_DIR} \
  --initial-cluster {initial_cluster}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

    with open(SYSTEMD_SERVICE_FILE, "w", encoding="utf-8", errors="replace") as f:
        f.write(service_content)
        log_and_print("✅ systemd 서비스 파일 생성 완료")

# 서비스 시작
def start_etcd_service():
    log_and_print("🔄 etcd 서비스 시작 중...")
    run_command("systemctl daemon-reload")
    run_command("systemctl enable etcd")
    run_command("systemctl start etcd")
    log_and_print("✅ etcd 서비스 시작 완료")

# 메인 함수
def main():
    log_and_print("=== etcd 설정 시작 ===")
    setup_environment_variables()
    install_etcd()
    setup_directories_and_certs()
    create_systemd_service()
    start_etcd_service()
    log_and_print("=== etcd 설정 완료 ===")

if __name__ == "__main__":
    main()
