import os
import paramiko
from scp import SCPClient

# 설정
WORKER_NODES = [
    {"hostname": "k8s-hardway-worker02", "ip": "192.168.89.22"},
    {"hostname": "k8s-hardway-worker03", "ip": "192.168.89.23"},
]
CERTS_DIR = "/root/hardway/certs"
DEST_DIR = "/etc/kubernetes"
SSH_USER = "root"
SSH_PASSWORD = "1234"  # SSH 비밀번호를 설정하세요.

# 전송할 파일 리스트
SSL_FILES_TO_TRANSFER = [
    "ca.crt",
]
KUBE_FILES_TO_TRANSFER = [
    "kube-proxy.kubeconfig",
]

# 로그 작성 함수
def log_message(message):
    print(message)

# 파일 전송 함수
def transfer_files_to_worker(worker):
    log_message(f"📦 {worker['hostname']}({worker['ip']})로 파일 전송 중...")

    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname=worker["ip"], username=SSH_USER, password=SSH_PASSWORD)

        with SCPClient(ssh.get_transport()) as scp:
            # SSL 디렉토리 생성 및 파일 전송
            ssh.exec_command(f"mkdir -p {DEST_DIR}/ssl")
            for file_name in SSL_FILES_TO_TRANSFER:
                src_path = os.path.join(CERTS_DIR, file_name)
                dest_path = f"{DEST_DIR}/ssl/{file_name}"
                scp.put(src_path, dest_path)
                log_message(f"✅ {file_name} 전송 완료: {src_path} -> {dest_path}")

            # kube-proxy.kubeconfig 파일 전송
            ssh.exec_command(f"mkdir -p {DEST_DIR}")
            for file_name in KUBE_FILES_TO_TRANSFER:
                src_path = os.path.join(CERTS_DIR, file_name)
                dest_path = f"{DEST_DIR}/{file_name}"
                scp.put(src_path, dest_path)
                log_message(f"✅ {file_name} 전송 완료: {src_path} -> {dest_path}")

        ssh.close()
        log_message(f"✅ {worker['hostname']}({worker['ip']})로 모든 파일 전송 완료")

    except Exception as e:
        log_message(f"❌ {worker['hostname']}({worker['ip']})로 파일 전송 실패: {e}")
        raise

# 메인 함수
def main():
    log_message("=== 파일 전송 스크립트 시작 ===")
    for worker in WORKER_NODES:
        transfer_files_to_worker(worker)
    log_message("=== 모든 파일 전송 완료 ===")

if __name__ == "__main__":
    main()