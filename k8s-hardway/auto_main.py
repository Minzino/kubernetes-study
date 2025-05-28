import paramiko
import os
import threading
import getpass

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

def auto_run_all():
    password = getpass.getpass("\nSSH 비밀번호 입력: ")

    tasks = [
        ("VIP 설정 (Pacemaker/Corosync)", lambda: run_local_script("pcs_setup.py")),
        ("인증서 생성", lambda: run_local_script("cert_create.py")),
        ("인증서 전송", lambda: run_local_script("cert_transfer.py")),
        ("ETCD 클러스터 구성", lambda: run_remote_scripts_concurrently(MASTER_NODES, "root", password, "etcd_setup.py")),
        ("ETCD 상태 검증", lambda: run_remote_scripts_concurrently(MASTER_NODES, "root", password, "etcd_verify.py")),
        ("Control Plane 설정", lambda: run_remote_scripts_concurrently(MASTER_NODES, "root", password, "control_plane_setup.py")),
        ("Worker Node 인증서 생성 및 전송", lambda: run_local_script("cert_create_worker.py")),
        ("Main Worker 노드 설정", lambda: run_remote_script(WORKER_NODES[0], "root", password, "worker_node_setup.py")),
        ("CNI 세팅 (Bastion Cilium)", lambda: run_local_script("cni_setup.py")),
        ("TLS Bootstrapping 설정", lambda: run_local_script("tls_setup.py")),
        ("Sub Worker Node 인증서 전송", lambda: run_local_script("cert_sub_worker_node_transfer.py")),
        ("Sub Worker Node 초기 세팅", lambda: run_remote_scripts_concurrently(WORKER_NODES[1:], "root", password, "sub_worker_node_setup.py")),
    ]

    for idx, (desc, task) in enumerate(tasks, start=1):
        log_message(f"▶ [{idx}/{len(tasks)}] {desc} 실행 중...")
        try:
            task()
            log_message(f"✅ [{idx}/{len(tasks)}] {desc} 완료")
        except Exception as e:
            log_message(f"❌ [{idx}/{len(tasks)}] {desc} 실패: {e}")
            break

    log_message("🚀 모든 작업이 완료되었습니다.")

if __name__ == "__main__":
    auto_run_all()
