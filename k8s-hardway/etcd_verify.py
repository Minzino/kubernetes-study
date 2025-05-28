import os
import subprocess
import time

# 기본 설정
LOG_FILE = "/root/hardway/etcd_verification.log"
ETCDCTL_API = "3"
ETCDCTL_CERT = "/etc/ssl/etcd/ssl/etcd-server.crt"
ETCDCTL_KEY = "/etc/ssl/etcd/ssl/etcd-server.key"
ETCDCTL_CACERT = "/etc/ssl/etcd/ssl/ca.crt"
ENDPOINTS = [
    "https://192.168.89.11:2379",
    "https://192.168.89.12:2379",
    "https://192.168.89.13:2379"
]

# 로그 작성 및 출력

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
        output = result.stdout.decode().strip()
        log_and_print(output)
        return output
    except subprocess.CalledProcessError as e:
        log_and_print(f"❌ 명령 실행 실패: {command}\n{e.stderr.decode().strip()}")
        return None

# etcd 클러스터 상태 확인
def check_etcd_status():
    log_and_print("🔄 etcd 클러스터 상태 확인 중...")

    # 환경 변수 설정
    os.environ["ETCDCTL_API"] = ETCDCTL_API
    os.environ["ETCDCTL_CERT"] = ETCDCTL_CERT
    os.environ["ETCDCTL_KEY"] = ETCDCTL_KEY
    os.environ["ETCDCTL_CACERT"] = ETCDCTL_CACERT

    # 상태 확인 명령어
    endpoint_str = ",".join(ENDPOINTS)
    command = f"etcdctl --endpoints={endpoint_str} endpoint status --write-out=table"
    status_output = run_command(command)

    if status_output:
        log_and_print("✅ etcd 클러스터 상태 확인 완료.")
    else:
        log_and_print("❌ etcd 클러스터 상태 확인 실패.")

# etcd 클러스터 헬스 체크
def check_etcd_health():
    log_and_print("🔄 etcd 클러스터 헬스 체크 중...")

    # 헬스 체크 명령어
    endpoint_str = ",".join(ENDPOINTS)
    command = f"etcdctl --endpoints={endpoint_str} endpoint health"
    health_output = run_command(command)

    if health_output:
        log_and_print("✅ etcd 클러스터 헬스 체크 완료.")
    else:
        log_and_print("❌ etcd 클러스터 헬스 체크 실패.")

# 메인 함수
def main():
    log_and_print("=== etcd 클러스터 검증 시작 ===")
    check_etcd_status()
    check_etcd_health()
    log_and_print("=== etcd 클러스터 검증 완료 ===")

if __name__ == "__main__":
    main()
