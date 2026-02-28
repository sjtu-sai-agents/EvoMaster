from io import StringIO

class OutputCapture:
    def __init__(self):
        self.stdout = StringIO()  # 捕获标准输出
        self.stderr = StringIO()  # 捕获标准错误

    def write(self, data: str):
        self.stdout.write(data)

    def flush(self):
        self.stdout.flush()
        self.stderr.flush()

    def get_stdout(self) -> str:
        return self.stdout.getvalue()

    def get_stderr(self) -> str:
        return self.stderr.getvalue()

    def close(self):
        self.stdout.close()
        self.stderr.close()

# 线程安全的输出管理器
class ThreadOutputManager:
    def get_capture(self) -> OutputCapture:
        return OutputCapture()  # 每次返回新的 capture