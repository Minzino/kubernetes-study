from paramiko import SSHClient, AutoAddPolicy

# 사용자 설정
SSH_USER = "root"
SSH_PASSWORD = "1234"

# 클러스터 설정
CLUSTER_NAME = "lbcluster"  # 클러스터 이름
BINDNETADDR = "192.168.89.0"  # IP 대역

# Master 노드 IP 목록
MASTER_NODES = [
    {"name": "master1", "ip": "192.168.89.11"},
    {"name": "master2", "ip": "192.168.89.12"},
    {"name": "master3", "ip": "192.168.89.13"},
]

# VIP 설정
VIP = "192.168.89.150"

# Corosync 설정 템플릿
COROSYNC_CONF_TEMPLATE = """totem {{
  version: 2
  cluster_name: {cluster_name}
  transport: udpu
  interface {{
    ringnumber: 0
    bindnetaddr: {bindnetaddr}
    broadcast: yes
    mcastport: 5405
  }}
}}

quorum {{
  provider: corosync_votequorum
  expected_votes: 3
}}

nodelist {{
{nodes}
}}

logging {{
  to_logfile: yes
  logfile: /var/log/corosync/corosync.log
  to_syslog: yes
  timestamp: on
}}
"""

# 초기 설정 명령어
INITIAL_SETUP_COMMANDS = [
    "DEBIAN_FRONTEND=noninteractive apt update -y",
    "DEBIAN_FRONTEND=noninteractive apt upgrade -y",
    "DEBIAN_FRONTEND=noninteractive apt install -y pacemaker corosync pcs",
    "systemctl enable corosync",
    "systemctl enable pcsd",
    "systemctl start corosync",
    "systemctl start pcsd",
]

def log_message(message):
    print(f"[LOG]: {message}")

# SSH 명령 실행 함수
def run_ssh_command(host, username, password, command):
    ssh = SSHClient()
    ssh.set_missing_host_key_policy(AutoAddPolicy())
    try:
        ssh.connect(host, username=username, password=password)
        stdin, stdout, stderr = ssh.exec_command(command)
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()
        if output:
            log_message(output)
        if error:
            log_message(f"Error on {host}: {error}")
        return output
    finally:
        ssh.close()

# 파일 전송 함수
def send_file(host, username, password, local_path, remote_path):
    ssh = SSHClient()
    ssh.set_missing_host_key_policy(AutoAddPolicy())
    try:
        ssh.connect(host, username=username, password=password)
        sftp = ssh.open_sftp()
        sftp.put(local_path, remote_path)
        log_message(f"File {local_path} sent to {host}:{remote_path}")
        sftp.close()
    finally:
        ssh.close()

# 초기 설정 실행 함수
def initial_setup():
    for master in MASTER_NODES:
        for command in INITIAL_SETUP_COMMANDS:
            log_message(f"Running on {master['name']}: {command}")
            run_ssh_command(master['ip'], SSH_USER, SSH_PASSWORD, command)

def generate_corosync_config():
    node_entries = "\n".join(
        [
            f"  node {{\n    ring0_addr: {node['ip']}\n    name: {node['name']}\n    nodeid: {index + 1}\n  }}"
            for index, node in enumerate(MASTER_NODES)
        ]
    )
    return COROSYNC_CONF_TEMPLATE.format(
        cluster_name=CLUSTER_NAME,
        bindnetaddr=BINDNETADDR,
        nodes=node_entries
    )

def deploy_corosync_config():
    config_content = generate_corosync_config()
    local_config_path = "/tmp/corosync.conf"
    with open(local_config_path, "w") as f:
        f.write(config_content)

    for master in MASTER_NODES:
        log_message(f"Deploying Corosync config to {master['name']}")
        send_file(master['ip'], SSH_USER, SSH_PASSWORD, local_config_path, "/etc/corosync/corosync.conf")

def generate_and_distribute_authkey():
    leader_node = MASTER_NODES[0]  # master1을 리더로 설정
    log_message(f"Generating authkey on {leader_node['name']}")
    run_ssh_command(leader_node['ip'], SSH_USER, SSH_PASSWORD, "corosync-keygen")

    local_authkey_path = "/tmp/authkey"
    remote_authkey_path = "/etc/corosync/authkey"

    # Retrieve authkey from the leader node
    ssh = SSHClient()
    ssh.set_missing_host_key_policy(AutoAddPolicy())
    ssh.connect(leader_node['ip'], username=SSH_USER, password=SSH_PASSWORD)
    sftp = ssh.open_sftp()
    sftp.get(remote_authkey_path, local_authkey_path)
    sftp.close()
    ssh.close()

    # Send authkey to other nodes
    for master in MASTER_NODES[1:]:
        log_message(f"Sending authkey to {master['name']}")
        send_file(master['ip'], SSH_USER, SSH_PASSWORD, local_authkey_path, remote_authkey_path)
        run_ssh_command(master['ip'], SSH_USER, SSH_PASSWORD, "chmod 600 /etc/corosync/authkey")

def setup_cluster_properties():
    for master in MASTER_NODES:
        log_message(f"Setting cluster properties on {master['name']}")
        run_ssh_command(master['ip'], SSH_USER, SSH_PASSWORD, "pcs property set stonith-enabled=false")
        run_ssh_command(master['ip'], SSH_USER, SSH_PASSWORD, "pcs resource defaults update resource-stickiness=60")

def setup_pacemaker_vip():
    leader_node = MASTER_NODES[0]  # master1을 리더로 설정
    log_message(f"Setting up VIP on {leader_node['name']}")
    vip_resource_command = (
        f"pcs resource create kubernetes_api_port ocf:heartbeat:IPaddr2 "
        f"ip={VIP} cidr_netmask=32 op monitor interval=5s "
        f"meta migration-threshold=2 failure-timeout=60s"
    )
    check_command = "pcs resource show kubernetes_api_port"
    delete_command = "pcs resource delete kubernetes_api_port"

    existing_vip = run_ssh_command(leader_node['ip'], SSH_USER, SSH_PASSWORD, check_command)
    if "kubernetes_api_port" in existing_vip:
        log_message("Existing VIP resource found, deleting...")
        run_ssh_command(leader_node['ip'], SSH_USER, SSH_PASSWORD, delete_command)

    run_ssh_command(leader_node['ip'], SSH_USER, SSH_PASSWORD, vip_resource_command)

# corosync 서비스 재시작 함수
def restart_corosync():
    for master in MASTER_NODES:
        log_message(f"Restarting corosync on {master['name']}")
        run_ssh_command(master['ip'], SSH_USER, SSH_PASSWORD, "systemctl restart corosync")

def main():
    log_message("Running initial setup on Master nodes...")
    initial_setup()

    log_message("Generating and distributing authkey...")
    generate_and_distribute_authkey()

    log_message("Deploying Corosync configuration...")
    deploy_corosync_config()

    log_message("Setting cluster properties...")
    setup_cluster_properties()

    log_message("Setting up Pacemaker Virtual IP...")
    setup_pacemaker_vip()

    log_message("Restarting Corosync services...")
    restart_corosync()

    log_message("Setup complete!")

if __name__ == "__main__":
    main()
