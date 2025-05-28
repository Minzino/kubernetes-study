import paramiko
import getpass
import os
import threading

def log_message(message):
    print(f"\n[LOG]: {message}")

def run_remote_script(host, username, password, script_name):
    try:
        log_message(f"🚀 {host}에서 {script_name} 실행 준비 중...")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(host, username=username, password=password)

        # 파일 전송 준비
        sftp = ssh.open_sftp()
        local_script_path = os.path.join(os.getcwd(), script_name)
        remote_script_path = f"/root/{script_name}"

        log_message(f"🚀 {host}로 {script_name} 전송 중...")
        sftp.put(local_script_path, remote_script_path)
        sftp.close()
        log_message(f"✅ {host}로 {script_name} 전송 완료: {remote_script_path}")

        # 스크립트 실행 전 권한 설정
        ssh.exec_command(f"chmod +x {remote_script_path}")

        # 스크립트 실행
        log_message(f"🚀 {host}에서 {script_name} 실행 중...")
        stdin, stdout, stderr = ssh.exec_command(f"python3 {remote_script_path}")

        output = stdout.read().decode('utf-8', errors='replace').strip()
        error = stderr.read().decode('utf-8', errors='replace').strip()

        if output:
            log_message(f"✅ {host}: {output}")
        if error:
            log_message(f"❌ {host} 실행 오류: {error}")

        ssh.close()
    except Exception as e:
        log_message(f"❌ {host}에서 {script_name} 실행 실패: {e}")

def run_remote_scripts_concurrently(hosts, username, password, script_name):
    threads = []
    for host in hosts:
        thread = threading.Thread(target=run_remote_script, args=(host, username, password, script_name))
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()

def run_local_script(script_name):
    try:
        script_path = os.path.join(os.getcwd(), script_name)
        log_message(f"🔧 Bastion 서버에서 {script_path} 실행 중...")
        os.system(f"python3 {script_path}")
    except Exception as e:
        log_message(f"❌ {script_name} 실행 실패: {e}")

# 서버 설정
MASTER_NODES = ["192.168.89.11", "192.168.89.12", "192.168.89.13"]
WORKER_NODES = ["192.168.89.21", "192.168.89.22", "192.168.89.23"]

def main():
    password = getpass.getpass("\nSSH 비밀번호 입력: ")

    while True:
        print("\n========= Kubernetes Hardway 클러스터 설정 =========")
        print("1. VIP 설정 (Pacemaker/Corosync)")
        print("2. 인증서 생성")
        print("3. 인증서 전송")
        print("4. ETCD 클러스터 구성")
        print("5. ETCD 상태 검증")
        print("6. Control Plane 설정")
        print("7. Worker Node 인증서 생성 및 전송")
        print("8. Main Worker 노드 설정")
        print("9. CNI 세팅 (Bastion Cilium)")
        print("10. TLS Bootstrapping 설정")
        print("11. Sub Worker Node 인증서 전송")
        print("12. Sub Worker Node 초기 세팅")
        print("13. 종료")
        print("===================================================")
        choice = input("실행할 작업을 선택하세요 (1-13): ")

        if choice == "1":
            run_local_script("pcs_setup.py")
        elif choice == "2":
            run_local_script("cert_create.py")
        elif choice == "3":
            run_local_script("cert_transfer.py")
        elif choice == "4":
            run_remote_scripts_concurrently(MASTER_NODES, "root", password, "etcd_setup.py")
        elif choice == "5":
            run_remote_scripts_concurrently(MASTER_NODES, "root", password, "etcd_verify.py")
        elif choice == "6":
            run_remote_scripts_concurrently(MASTER_NODES, "root", password, "control_plane_setup.py")
        elif choice == "7":
            run_local_script("cert_create_worker.py")
        elif choice == "8":
            run_remote_script(WORKER_NODES[0], "root", password, "worker_node_setup.py")
        elif choice == "9":
            run_local_script("cni_setup.py")
        elif choice == "10":
            run_local_script("tls_setup.py")
        elif choice == "11":
            run_local_script("cert_sub_worker_node_transfer.py")
        elif choice == "12":
            run_remote_scripts_concurrently(WORKER_NODES[1:], "root", password, "sub_worker_node_setup.py")
        elif choice == "13":
            log_message("클러스터 설정 종료.")
            break
        else:
            log_message("❌ 잘못된 입력입니다. 다시 시도하세요.")

if __name__ == "__main__":
    main()
