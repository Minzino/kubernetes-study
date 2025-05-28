import os
import subprocess
import paramiko
from scp import SCPClient
import time

# 설정
WORKER_NODES = [
    {"hostname": "k8s-hardway-worker01", "ip": "192.168.89.21", "manual_cert": True},
    {"hostname": "k8s-hardway-worker02", "ip": "192.168.89.22", "manual_cert": False},
    {"hostname": "k8s-hardway-worker03", "ip": "192.168.89.23", "manual_cert": False},
]
CERT_DIR = "/root/hardway/certs"
LOG_FILE = f"{CERT_DIR}/worker_cert_setup.log"
CLUSTER_NAME = "minje-k8s-hardway"
API_SERVER_ADDRESS = "192.168.89.150"
SSH_USER = "root"
SSH_PASSWORD = "1234"


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


# 디렉토리 생성 함수
def create_cert_directory():
    if not os.path.exists(CERT_DIR):
        os.makedirs(CERT_DIR)
        log_message(f"✅ 디렉토리 생성 완료: {CERT_DIR}")
    else:
        log_message(f"⚠️ 디렉토리가 이미 존재합니다: {CERT_DIR}")


# Worker Node 1 인증서 생성
def create_worker_certificates(node):
    log_message(f"🔄 {node['hostname']} 인증서 생성 중...")
    openssl_config = f"{CERT_DIR}/openssl-{node['hostname']}.cnf"

    # OpenSSL 구성 파일 생성
    with open(openssl_config, "w") as config_file:
        config_file.write(f"""
[req]
req_extensions = v3_req
distinguished_name = req_distinguished_name

[req_distinguished_name]

[v3_req]
basicConstraints = CA:FALSE
keyUsage = nonRepudiation, digitalSignature, keyEncipherment
subjectAltName = @alt_names

[alt_names]
IP.1 = {node['ip']}
DNS.1 = {node['hostname']}
""")
    # 개인 키 생성
    run_command(f"openssl genrsa -out {CERT_DIR}/{node['hostname']}.key 2048")
    # CSR 생성
    run_command(
        f"openssl req -new -key {CERT_DIR}/{node['hostname']}.key -subj \"/CN=system:node:{node['hostname']}/O=system:nodes\" "
        f"-out {CERT_DIR}/{node['hostname']}.csr -config {openssl_config}"
    )
    # 인증서 서명
    run_command(
        f"openssl x509 -req -in {CERT_DIR}/{node['hostname']}.csr -CA {CERT_DIR}/ca.crt -CAkey {CERT_DIR}/ca.key "
        f"-CAcreateserial -out {CERT_DIR}/{node['hostname']}.crt -extensions v3_req -extfile {openssl_config} -days 365"
    )
    log_message(f"✅ {node['hostname']} 인증서 생성 완료")


# kubeconfig 생성 함수
def create_worker_kubeconfig(node):
    log_message(f"🔄 {node['hostname']} kubeconfig 생성 중...")
    kubeconfig_file = f"{CERT_DIR}/{node['hostname']}.kubeconfig"

    # 클러스터 설정
    run_command(
        f"kubectl config set-cluster {CLUSTER_NAME} "
        f"--certificate-authority={CERT_DIR}/ca.crt --embed-certs=true "
        f"--server=https://{API_SERVER_ADDRESS}:6443 --kubeconfig={kubeconfig_file}"
    )
    # 사용자 자격 증명 설정
    run_command(
        f"kubectl config set-credentials system:node:{node['hostname']} "
        f"--client-certificate={CERT_DIR}/{node['hostname']}.crt --client-key={CERT_DIR}/{node['hostname']}.key "
        f"--embed-certs=true --kubeconfig={kubeconfig_file}"
    )
    # 컨텍스트 설정
    run_command(
        f"kubectl config set-context default "
        f"--cluster={CLUSTER_NAME} --user=system:node:{node['hostname']} --kubeconfig={kubeconfig_file}"
    )
    # 기본 컨텍스트 설정
    run_command(f"kubectl config use-context default --kubeconfig={kubeconfig_file}")
    log_message(f"✅ {node['hostname']} kubeconfig 생성 완료")


# 인증서 전송 함수
def transfer_certificates(node):
    log_message(f"📦 {node['hostname']}({node['ip']})에 인증서 전송 중...")

    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname=node["ip"], username=SSH_USER, password=SSH_PASSWORD)

        with SCPClient(ssh.get_transport()) as scp:
            ssh.exec_command(f"mkdir -p /etc/kubernetes/ssl")
            cert_files = [
                f"{node['hostname']}.crt",
                f"{node['hostname']}.key",
                "ca.crt",
                f"{node['hostname']}.kubeconfig"
            ]
            for cert in cert_files:
                src_path = os.path.join(CERT_DIR, cert)
                dest_path = f"/etc/kubernetes/ssl/{cert}" if cert != f"{node['hostname']}.kubeconfig" else f"/etc/kubernetes/{cert}"
                scp.put(src_path, dest_path)
                log_message(f"✅ {cert} 전송 완료: {node['hostname']}({node['ip']}) -> {dest_path}")

        ssh.close()

    except Exception as e:
        log_message(f"❌ {node['hostname']}({node['ip']})에 인증서 전송 실패: {e}")
        raise


# TLS Bootstrapping 구성 생성 함수
def configure_tls_bootstrap():
    log_message("🔄 TLS Bootstrapping 구성 생성 중...")
    bootstrap_file = f"{CERT_DIR}/bootstrap-token.yaml"
    with open(bootstrap_file, "w") as file:
        file.write(f"""
apiVersion: v1
kind: Secret
metadata:
  name: bootstrap-token-07401b
  namespace: kube-system
type: bootstrap.kubernetes.io/token
stringData:
  description: "Bootstrap token for Worker Nodes"
  token-id: 07401b
  token-secret: f395accd246ae52d
  usage-bootstrap-authentication: "true"
  usage-bootstrap-signing: "true"
  auth-extra-groups: system:bootstrappers:worker
""")
    run_command(f"kubectl apply -f {bootstrap_file}")
    log_message("✅ TLS Bootstrapping 구성 생성 완료")


# 메인 함수
def main():
    log_message("=== Worker Node 인증서 생성 및 TLS Bootstrapping 구성 시작 ===")
    create_cert_directory()

    for node in WORKER_NODES:
        if node["manual_cert"]:
            create_worker_certificates(node)
            create_worker_kubeconfig(node)
            transfer_certificates(node)

    configure_tls_bootstrap()
    log_message("=== 모든 작업 완료 ===")


if __name__ == "__main__":
    main()
