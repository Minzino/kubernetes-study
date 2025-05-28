import os
import paramiko
from scp import SCPClient
import time

# 설정
WORKER_NODES = [
    {"hostname": "k8s-hardway-worker01", "ip": "192.168.89.21", "manual_cert": True},
    {"hostname": "k8s-hardway-worker02", "ip": "192.168.89.22", "manual_cert": False},
    {"hostname": "k8s-hardway-worker03", "ip": "192.168.89.23", "manual_cert": False},
]
MASTER_NODES = [
    {"hostname": "k8s-hardway-master01", "ip": "192.168.89.11"},
    {"hostname": "k8s-hardway-master02", "ip": "192.168.89.12"},
    {"hostname": "k8s-hardway-master03", "ip": "192.168.89.13"},
]
ALL_NODES = WORKER_NODES + MASTER_NODES
CERT_DIR = "/root/hardway/certs"
LOG_FILE = f"{CERT_DIR}/node_cert_transfer.log"
SSH_USER = "root"
SSH_PASSWORD = "1234"


# 로그 작성 함수
def log_message(message):
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    with open(LOG_FILE, "a", encoding="utf-8") as log:
        log.write(f"{timestamp} - {message}\n")
    print(message)


# 디렉토리 생성 함수
def create_cert_directory():
    if not os.path.exists(CERT_DIR):
        os.makedirs(CERT_DIR)
        log_message(f"✅ 디렉토리 생성 완료: {CERT_DIR}")
    else:
        log_message(f"⚠️ 디렉토리가 이미 존재합니다: {CERT_DIR}")


# 인증서 전송 함수
def transfer_certificates():
    log_message("🔄 모든 노드로 인증서 전송 시작...")

    try:
        for node in ALL_NODES:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(hostname=node["ip"], username=SSH_USER, password=SSH_PASSWORD)

            with SCPClient(ssh.get_transport()) as scp:
                ssh.exec_command("mkdir -p /home/ubuntu/hardway/certs")

                if "master" in node["hostname"]:
                    cert_files = [
                        "ca.crt", "ca.key", "kube-apiserver.key", "kube-apiserver.crt",
                        "service-account.key", "service-account.crt",
                        "etcd-server.key", "etcd-server.crt",
                        "admin.kubeconfig", "kube-controller-manager.kubeconfig", "kube-scheduler.kubeconfig"
                    ]
                else:
                    cert_files = ["ca.crt", "kube-proxy.kubeconfig"]

                for cert in cert_files:
                    src_path = os.path.join(CERT_DIR, cert)
                    dest_path = f"/home/ubuntu/hardway/certs/{cert}"
                    scp.put(src_path, dest_path)
                    log_message(f"✅ {cert} 전송 완료: {node['hostname']}({node['ip']}) -> {dest_path}")

            ssh.close()

    except Exception as e:
        log_message(f"❌ 인증서 전송 실패: {e}")
        raise

    log_message("✅ 모든 노드로 인증서 전송 완료")


# 메인 함수
def main():
    log_message("=== 인증서 전송 스크립트 시작 ===")
    create_cert_directory()
    transfer_certificates()
    log_message("=== 인증서 전송 스크립트 완료 ===")


if __name__ == "__main__":
    main()
