from collections.abc import Callable
import json
from os import environ, listdir
from zipfile import ZIP_BZIP2, ZipFile


default_weight_map = {
    "thin": 100,
    "extralight": 200,
    "light": 300,
    "regular": 400,
    "medium": 500,
    "semibold": 600,
    "bold": 700,
    "extrabold": 800,
}


def write_text(file_path: str, content: str, mode: str = "w") -> None:
    if not isinstance(file_path, str) or not file_path:
        raise ValueError("Invalid file path")
    if not isinstance(content, str):
        raise ValueError("Invalid content")
    with open(file_path, encoding="utf-8", mode=mode, newline="\n") as file:
        file.write(content)


def write_json(file_path: str, data: dict) -> None:
    with open(file_path, "w", encoding="utf-8", newline="\n") as file:
        json.dump(data, file, indent=2)


def read_json(file_path: str) -> dict:
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


def read_text(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as file:
        return file.read()


def is_ci():
    ci_envs = [
        "JENKINS_HOME",
        "TRAVIS",
        "CIRCLECI",
        "GITHUB_ACTIONS",
        "GITLAB_CI",
        "TF_BUILD",
    ]

    for env in ci_envs:
        if environ.get(env):
            return True

    return False


def archive(source: str, target: str, filter: Callable[[str], bool]):
    with ZipFile(target, "w", compression=ZIP_BZIP2, compresslevel=9) as zip_file:
        for file in listdir(source):
            file_path = joinPaths(source, file)
            if filter(file_path):
                zip_file.write(file_path, file)

    zip_file.close()
    print(f"📦 Package {target}")


def joinPaths(*args: str) -> str:
    return "/".join(args)
