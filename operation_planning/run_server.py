import argparse
from operation_planning.app import serve


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="能智核本地实时计算服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18765)
    args = parser.parse_args()
    serve(args.host, args.port)
