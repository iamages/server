import uvicorn
from argparse import ArgumentParser

if __name__ == "__main__":
    arg_parser = ArgumentParser(
        description="Iamages server."
    )
    arg_parser.add_argument(
        "--address",
        action="store",
        default="127.0.0.1",
        help="Host address."
    )
    arg_parser.add_argument(
        "--port",
        action="store",
        default="8000",
        help="Host port."
    )
    arg_parsed = arg_parser.parse_args()
    uvicorn.run("server.main:app", host=arg_parsed.address, port=arg_parsed.port)