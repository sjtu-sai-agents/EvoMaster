"""本地环境使用示例

演示如何使用 LocalSession 在本地执行命令和作业。
"""

from evomaster.agent.session import LocalSession, LocalSessionConfig


def example_basic_session():
    """示例 1: 基础 Session 使用"""
    print("\n" + "=" * 60)
    print("示例 1: 基础 Session 使用")
    print("=" * 60)

    with LocalSession() as session:
        # 执行简单命令
        result = session.exec_bash("python --version")
        print(f"Python 版本: {result['stdout'].strip()}")

        # 执行多行命令
        cmd = """
cat > /tmp/test.txt << 'EOF'
Hello, World!
This is a test file.
EOF
cat /tmp/test.txt
"""
        result = session.exec_bash(cmd)
        print(f"\n文件内容:\n{result['stdout']}")

        # 查看退出码
        print(f"退出码: {result['exit_code']}")


def example_job_submission():
    """示例 2: 命令执行"""
    print("\n" + "=" * 60)
    print("示例 2: 命令执行")
    print("=" * 60)

    with LocalSession() as session:
        # 执行多个命令
        print("\n执行命令中...")

        for i in range(3):
            command = f"echo 'Job {i+1}' && sleep 1 && echo 'Job {i+1} completed'"
            result = session.exec_bash(command)
            print(f"  命令 {i+1}:")
            print(f"    退出码: {result['exit_code']}")
            print(f"    输出: {result['stdout'].strip()[:50]}")


def example_file_operations():
    """示例 3: 文件上传/下载"""
    print("\n" + "=" * 60)
    print("示例 3: 文件上传/下载")
    print("=" * 60)

    with LocalSession() as session:
        # 创建本地文件
        import tempfile
        from pathlib import Path

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            local_file = f.name
            f.write("Hello from local file!\n")
            f.write("This is test content.")

        print(f"\n创建本地文件: {local_file}")

        # 上传文件
        remote_file = "/tmp/uploaded_test.txt"
        session.upload(local_file, remote_file)
        print(f"上传到: {remote_file}")

        # 读取上传的文件
        content = session.read_file(remote_file)
        print(f"\n上传文件的内容:\n{content}")

        # 下载文件
        data = session.download(remote_file)
        print(f"下载成功: {len(data)} 字节")

        # 清理
        Path(local_file).unlink()


def example_environment_variables():
    """示例 4: 环境变量和工作目录"""
    print("\n" + "=" * 60)
    print("示例 4: 环境变量和工作目录")
    print("=" * 60)

    config = LocalSessionConfig(
        timeout=30,
        workspace_path="/tmp",
    )

    with LocalSession(config) as session:
        # 在指定的工作目录执行命令
        result = session.exec_bash("pwd && ls -la | head -5")
        print(f"\n工作目录内容:\n{result['stdout']}")

        # 设置环境变量并使用
        cmd = """
export MY_VAR="Hello from Environment"
echo "Variable: $MY_VAR"
"""
        result = session.exec_bash(cmd)
        print(f"\n环境变量测试:\n{result['stdout']}")


def main():
    """运行所有示例"""
    print("\n" + "=" * 60)
    print("本地 Session (LocalSession) 使用示例")
    print("=" * 60)

    example_basic_session()
    example_job_submission()
    example_file_operations()
    example_environment_variables()

    print("\n" + "=" * 60)
    print("所有示例运行完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
