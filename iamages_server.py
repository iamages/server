__version__ = "2.1.0"
__copyright__ = "© jkelol111 et al 2020-present"

import os
import json
import databases
import random
import bcrypt
import base64
import hashlib
import filetype
import string
import mimetypes
import PIL.Image
import aiofiles
import aiofiles.os
import shutil
import starlette.applications
import starlette.endpoints
import starlette.routing
import starlette.staticfiles
import starlette.templating
import starlette.middleware
import starlette.background
import starlette.middleware.cors
import starlette.middleware.gzip
import starlette.responses
import starlette.exceptions

IAMAGES_PATH = os.path.dirname(os.path.realpath(__file__))

server_config = json.load(open("servercfg.json", "r"))

SUPPORTED_FORMAT = 2

if server_config["files"]["storage"]["format"] != SUPPORTED_FORMAT:
    print(f'Current storage format is not supported. (expected: {SUPPORTED_FORMAT}, got: {server_config["files"]["format"]})')
    exit(1) 

if not os.path.isdir(server_config["files"]["storage"]["directory"]):
    os.makedirs(server_config["files"]["storage"]["directory"])

IAMAGESDB_PATH = os.path.join(server_config["files"]["storage"]["directory"], "iamages.db")
iamagesdb = databases.Database("sqlite:///" + IAMAGESDB_PATH)

FILES_PATH = os.path.join(server_config["files"]["storage"]["directory"], "files")
if not os.path.isdir(FILES_PATH):
    os.makedirs(FILES_PATH)

THUMBS_PATH = os.path.join(server_config["files"]["storage"]["directory"], "thumbs")
if not os.path.isdir(THUMBS_PATH):
    os.makedirs(THUMBS_PATH)

templates = starlette.templating.Jinja2Templates(directory=os.path.join(IAMAGES_PATH, "templates"))


class SharedFunctions:
    @staticmethod
    async def delete_file(FileID: int):
        ex_file_directory = os.path.join(FILES_PATH, str(FileID))
        ex_thumb_directory = os.path.join(THUMBS_PATH, str(FileID))
        file_links = await iamagesdb.fetch_all("SELECT FileID FROM Files WHERE FileLink = :FileID", {
            "FileID": FileID
        })
        if file_links:
            ex_file_info = await iamagesdb.fetch_one("SELECT FileName, FileMime, FileWidth, FileHeight, FileHash FROM Files WHERE FileID = :FileID", {
                "FileID": FileID
            })
            new_file_directory = os.path.join(FILES_PATH, str(file_links[0][0]))
            if not os.path.isdir(new_file_directory):
                await aiofiles.os.mkdir(new_file_directory)
            new_thumb_directory = os.path.join(THUMBS_PATH, str(file_links[0][0]))
            if not os.path.isdir(new_thumb_directory):
                await aiofiles.os.mkdir(new_thumb_directory)
            new_file_name = '' + (random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(6)) + mimetypes.guess_extension(ex_file_info[1])
            async with aiofiles.open(os.path.join(ex_file_directory, ex_file_info[0]), "rb") as ex_file:
                async with aiofiles.open(os.path.join(new_file_directory, new_file_name), "wb") as new_file:
                    await new_file.write(await ex_file.read())
            ex_thumb_name = os.path.join(ex_thumb_directory, ex_file_info[0])
            if os.path.isfile(ex_thumb_name):
                async with aiofiles.open(ex_thumb_name, "rb") as ex_thumb:
                    async with aiofiles.open(os.path.join(new_thumb_directory, new_file_name), "wb") as new_thumb:
                        await new_thumb.write(await ex_thumb.read())
            else:
                await SharedFunctions.create_thumb(file_links[0][0], new_file_name, ex_file_info[1])
            await iamagesdb.execute("UPDATE Files SET FileName = :FileName, FileMime = :FileMime, FileWidth = :FileWidth, FileHeight = :FileHeight, FileHash = :FileHash, FileLink = :FileLink WHERE FileID = :FileID", {
                "FileName": new_file_name,
                "FileMime": ex_file_info[1],
                "FileWidth": ex_file_info[2],
                "FileHeight": ex_file_info[3],
                "FileHash": ex_file_info[4],
                "FileLink": None,
                "FileID": file_links[0][0] 
            })
            for file in range(1, len(file_links)):
                await iamagesdb.execute("UPDATE Files SET FileLink = :FileLink WHERE FileID = :FileID", {
                    "FileLink": file_links[0][0],
                    "FileID": file_links[file][0]
                })
        if os.path.isdir(ex_file_directory):
            shutil.rmtree(ex_file_directory)
        if os.path.isdir(ex_thumb_directory):
            shutil.rmtree(ex_thumb_directory)
        await iamagesdb.execute("DELETE FROM Files WHERE FileID = :FileID", {
            "FileID": FileID
        })
        await iamagesdb.execute("DELETE FROM Files_Users WHERE FileID = :FileID", {
            "FileID": FileID
        })

    @staticmethod
    async def check_user(UserName: str, UserPassword: str) -> int:
        users = await iamagesdb.fetch_all("SELECT UserID, UserPassword FROM Users WHERE UserName = :UserName", {
            "UserName": UserName
        })

        if not users:
            return None

        for user in users:
            if bcrypt.checkpw(bytes(UserPassword, "utf-8"), user[1]):
                return user[0]
        return None

    @staticmethod
    async def check_file_belongs(FileID: int, UserID: int) -> int:
        if FileID == await iamagesdb.fetch_val("SELECT FileID FROM Files_Users WHERE FileID = :FileID AND UserID = :UserID", {
            "FileID": FileID,
            "UserID": UserID
        }):
            return FileID
        else:
            return None

    @staticmethod
    async def process_auth_header(headers: list) -> int:
        if "Authorization" not in headers:
            return None
        auth = headers["Authorization"]
        scheme, credentials = auth.split(" ")
        if scheme.lower() != "basic":
            return None
        try:
            credentials_decoded = base64.b64decode(credentials).decode("utf-8")
        except:
            return None

        UserName, _, UserPassword = credentials_decoded.partition(":")
        UserID = await SharedFunctions.check_user(UserName, UserPassword)
        if UserID:
            return UserID
        else:
            return None

    @staticmethod
    async def create_thumb(FileID: int, FileName: str, FileMime: str) -> None:
        thumb_folder_path = os.path.join(THUMBS_PATH, str(FileID))
        if not os.path.isdir(thumb_folder_path):
            await aiofiles.os.mkdir(thumb_folder_path)
        new_thumb_path = os.path.join(thumb_folder_path, FileName)
        with PIL.Image.open(os.path.join(FILES_PATH, str(FileID), FileName)) as img:
            img.thumbnail((600, 600), PIL.Image.LANCZOS)
            if FileMime == "image/gif":
                img.save(new_thumb_path, save_all=True)
            else:
                img.save(new_thumb_path)

    @staticmethod
    async def parse_request_json(request):
        try:
            return await request.json()
        except json.decoder.JSONDecodeError as error_str:
            raise starlette.exceptions.HTTPException(400)


class Private:
    class TOS(starlette.endpoints.HTTPEndpoint):
        async def get(self, request):
            await request.send_push_promise("/private/static/css/bulma.min.css")
            return templates.TemplateResponse("tos.html", {
                "request": request,
                "owner": server_config["meta"]["owner"]
            })

    class PrivacyPolicy(starlette.endpoints.HTTPEndpoint):
        async def get(self, request):
            await request.send_push_promise("/private/static/css/bulma.min.css")
            return templates.TemplateResponse("privacy.html", {
                "request": request,
                "owner": server_config["meta"]["owner"]
            })


class Docs(starlette.endpoints.HTTPEndpoint):
    async def get(self, request):
        await request.send_push_promise("/private/static/css/bulma.min.css")
        return templates.TemplateResponse("api-doc.html", {
            "request": request,
            "supported_filemimes": server_config["files"]["accept_filemimes"],
            "owner": server_config["meta"]["owner"]
        })


class Latest(starlette.endpoints.HTTPEndpoint):
    async def get(self, request):
        response_body = {
            "FileIDs": []
        }
        FileIDs = await iamagesdb.fetch_all("SELECT FileID FROM Files WHERE FilePrivate = 0 AND FileExcludeSearch = 0 ORDER BY FileID DESC LIMIT 10")
        for FileID in FileIDs:
            response_body["FileIDs"].append(FileID[0])
        return starlette.responses.JSONResponse(response_body)


class Random(starlette.endpoints.HTTPEndpoint):
    async def get(self, request):
        total_files = await iamagesdb.fetch_val("SELECT COUNT(FileID) FROM Files")
        if not total_files > 2:
            raise starlette.exceptions.HTTPException(503)

        FileID = 0

        while FileID == 0:
            FileID = random.randint(1, total_files)
            test_FileID = await iamagesdb.fetch_one("SELECT FileID From Files WHERE FileID = :FileID AND FilePrivate = 0 AND FileExcludeSearch = 0", {
                "FileID": FileID
            })
            if not test_FileID:
                FileID = 0
        
        return starlette.responses.RedirectResponse(request.url_for("info", FileID=FileID))


class Upload(starlette.endpoints.HTTPEndpoint):
    async def put(self, request):
        request_body = await SharedFunctions.parse_request_json(request)

        if "FileData" not in request_body or "FileNSFW" not in request_body or "FileDescription" not in request_body or type(request_body["FileData"]) != str or type(request_body["FileNSFW"]) != bool or type(request_body["FileDescription"]) != str:
            raise starlette.exceptions.HTTPException(400)

        UserID = None

        if "UserName" in request_body and "UserPassword" in request_body and type(request_body["UserName"]) == str and type(request_body["UserPassword"]) == str:
            UserID = await SharedFunctions.check_user(request_body["UserName"], request_body["UserPassword"])
            if not UserID:
                raise starlette.exceptions.HTTPException(401)

        if not ((len(request_body["FileData"]) * 3) / 4) < server_config["files"]["max_size"]:
            raise starlette.exceptions.HTTPException(413)

        await iamagesdb.execute("INSERT INTO Files (FileDescription, FileNSFW, FileCreatedDate) VALUES (:FileDescription, :FileNSFW, datetime('now'))", {
            "FileDescription": request_body["FileDescription"],
            "FileNSFW": request_body["FileNSFW"]
        })

        FileID = (await iamagesdb.fetch_one("SELECT FileID FROM Files ORDER BY FileID DESC"))[0]
        FileData = base64.b64decode(request_body["FileData"])
        FileHash = hashlib.blake2b(FileData).hexdigest()

        duplicate_exists = await iamagesdb.fetch_all("SELECT FileID FROM Files WHERE FileHash = :FileHash AND FilePrivate = 0", {
            "FileHash": FileHash
        })

        default_query_FilePrivate = "UPDATE Files SET FilePrivate = :FilePrivate WHERE FileID = " + str(FileID)
        default_query_FileExcludeSearch = "UPDATE Files SET FileExcludeSearch = :FileExcludeSearch WHERE FileID = " + str(FileID)

        response_body = {
            "FileID": None
        }

        if duplicate_exists:
            await iamagesdb.execute("UPDATE Files SET FileLink = :FileLink WHERE FileID = :FileID", {
                "FileLink": duplicate_exists[0][0],
                "FileID": FileID
            })
            if UserID:
                await iamagesdb.execute("INSERT INTO Files_Users (FileID, UserID) VALUES (:FileID, :UserID)", {
                    "FileID": FileID,
                    "UserID": UserID
                })
                if "FilePrivate" in request_body and type(request_body["FilePrivate"]) == bool:
                    await iamagesdb.execute(default_query_FilePrivate, {
                        "FilePrivate": request_body["FilePrivate"]
                    })
                else:
                    await iamagesdb.execute(default_query_FilePrivate, {
                        "FilePrivate": False
                    })
            else:
                await iamagesdb.execute(default_query_FilePrivate, {
                    "FilePrivate": False
                })

            if "FileExcludeSearch" in request_body and type(request_body["FileExcludeSearch"]) == bool:
                await iamagesdb.execute(default_query_FileExcludeSearch, {
                    "FileExcludeSearch": request_body["FileExcludeSearch"]
                })
            else:
                await iamagesdb.execute(default_query_FileExcludeSearch, {
                    "FileExcludeSearch": False
                })

            response_body["FileID"] = FileID
            return starlette.responses.JSONResponse(response_body)
        else:
            file_folder_path = os.path.join(FILES_PATH, str(FileID))
            if not os.path.isdir(file_folder_path):
                await aiofiles.os.mkdir(file_folder_path)

            file_path = os.path.join(file_folder_path, "unprocessed.image")
            async with aiofiles.open(file_path, "wb") as file:
                await file.write(FileData)

            file_type = filetype.guess(file_path)
            if file_type.mime not in server_config["files"]["accept_filemimes"]:
                await SharedFunctions.delete_file(FileID)
                raise starlette.exceptions.HTTPException(415)

            random_file_name = '' + (random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(6)) + "." + file_type.extension

            new_file_path = os.path.join(file_folder_path, random_file_name)

            with PIL.Image.open(file_path) as img:
                if file_type.mime == "image/gif":
                    img.save(new_file_path, save_all=True)
                else:
                    img.save(new_file_path)
                await iamagesdb.execute("UPDATE Files SET FileName = :FileName, FileWidth = :FileWidth, FileHeight = :FileHeight, FileMime = :FileMime, FileHash = :FileHash WHERE FileID = :FileID", {
                    "FileName": random_file_name,
                    "FileWidth": img.size[0],
                    "FileHeight": img.size[1],
                    "FileMime": file_type.mime,
                    "FileHash": FileHash,
                    "FileID": FileID
                })

            await aiofiles.os.remove(file_path)

            if UserID:
                await iamagesdb.execute("INSERT INTO Files_Users (FileID, UserID) VALUES (:FileID, :UserID)", {
                    "FileID": FileID,
                    "UserID": UserID
                })
                if "FilePrivate" in request_body and type(request_body["FilePrivate"]) == bool:
                    await iamagesdb.execute(default_query_FilePrivate, {
                        "FilePrivate": request_body["FilePrivate"]
                    })
                else:
                    await iamagesdb.execute(default_query_FilePrivate, {
                        "FilePrivate": False
                    })
            else:
                await iamagesdb.execute(default_query_FilePrivate, {
                    "FilePrivate": False
                })

            if "FileExcludeSearch" in request_body and type(request_body["FileExcludeSearch"]) == bool:
                await iamagesdb.execute(default_query_FileExcludeSearch, {
                    "FileExcludeSearch": request_body["FileExcludeSearch"]
                })
            else:
                await iamagesdb.execute(default_query_FileExcludeSearch, {
                    "FileExcludeSearch": False
                })
                
            response_body["FileID"] = FileID
            bg_task = starlette.background.BackgroundTask(SharedFunctions.create_thumb, FileID=FileID, FileName=random_file_name, FileMime=file_type.mime)
            return starlette.responses.JSONResponse(response_body, background=bg_task)


class Modify(starlette.endpoints.HTTPEndpoint):
    async def patch(self, request):
        request_body = await SharedFunctions.parse_request_json(request)

        if "UserName" not in request_body or "UserPassword" not in request_body or "FileID" not in request_body or "Modifications" not in request_body or type(request_body["UserName"]) != str or type(request_body["UserPassword"]) != str or type(request_body["FileID"]) != int or type(request_body["Modifications"]) != dict:
            raise starlette.exceptions.HTTPException(400)

        UserID = await SharedFunctions.check_user(request_body["UserName"], request_body["UserPassword"])

        if not UserID:
            raise starlette.exceptions.HTTPException(401)

        FileID = await SharedFunctions.check_file_belongs(request_body["FileID"], UserID)
        if FileID != request_body["FileID"]:
            raise starlette.exceptions.HTTPException(404)

        basic_query = "UPDATE Files SET {0} = :value WHERE FileID = " + str(FileID)

        response_body = {
            "FileID": None,
            "Modifications": []
        }

        response_body["FileID"] = FileID

        for modification in request_body["Modifications"]:
            if modification in ["FileDescription", "FileNSFW", "FilePrivate", "FileExcludeSearch"]:
                modification_query = basic_query.format(modification)
                await iamagesdb.execute(modification_query, {
                    "value": request_body["Modifications"][modification]
                })
            elif modification == "DeleteFile":
                await SharedFunctions.delete_file(FileID)
            response_body["Modifications"].append(modification)

        return starlette.responses.JSONResponse(response_body)


class Info(starlette.endpoints.HTTPEndpoint):
    async def get(self, request):
        FileID = int(request.path_params["FileID"])
        FileInformation = await iamagesdb.fetch_one("SELECT FileDescription, FileNSFW, FilePrivate, FileMime, FileWidth, FileHeight, FileCreatedDate, FileLink, FileExcludeSearch FROM Files WHERE FileID = :FileID", {
            "FileID": FileID
        })
        
        if not FileInformation:
            raise starlette.exceptions.HTTPException(404)
        
        FilePrivate = bool(FileInformation[2])
        if not FilePrivate:
            return await self.send_info(FileID, FilePrivate, FileInformation)

        UserID = await SharedFunctions.process_auth_header(request.headers)
        if not UserID or FileID != await SharedFunctions.check_file_belongs(FileID, UserID):
            raise starlette.exceptions.HTTPException(401)
        
        return await self.send_info(FileID, FilePrivate, FileInformation)

    async def send_info(self, FileID, FilePrivate, FileInformation):
        response_body = {
            "FileID": None,
            "FileDescription": None,
            "FileNSFW": None,
            "FilePrivate": None,
            "FileMime": None,
            "FileWidth": None,
            "FileHeight": None,
            "FileCreatedDate": None,
            "FileExcludeSearch": None
        }
        response_body["FileID"] = FileID
        response_body["FileDescription"] = FileInformation[0]
        response_body["FileNSFW"] = bool(FileInformation[1])
        response_body["FilePrivate"] = FilePrivate

        if FileInformation[7]:
            linked_FileInformation = await iamagesdb.fetch_one("SELECT FileMime, FileWidth, FileHeight FROM Files WHERE FileID = :FileID", {
                "FileID": FileInformation[7]
            })
            response_body["FileMime"] = linked_FileInformation[0]
            response_body["FileWidth"] = linked_FileInformation[1]
            response_body["FileHeight"] = linked_FileInformation[2]
        else:
            response_body["FileMime"] = FileInformation[3]
            response_body["FileWidth"] = FileInformation[4]
            response_body["FileHeight"] = FileInformation[5]

        response_body["FileCreatedDate"] = FileInformation[6]
        response_body["FileExcludeSearch"] = bool(FileInformation[8])

        return starlette.responses.JSONResponse(response_body)


class Infos(starlette.endpoints.HTTPEndpoint):
    async def post(self, request):
        request_body = await SharedFunctions.parse_request_json(request)
        response_body = []

        UserID = None
        if "UserName" in request_body or "UserPassword" in request_body and type(request_body["UserName"]) == str and type(request_body["UserPassword"]) == str:
            UserID = await SharedFunctions.check_user(request_body["UserName"], request_body["UserPassword"])

        processed_FileIDs = []

        for FileID in request_body["FileIDs"]:
            if FileID in processed_FileIDs:
                continue

            if type(FileID) != int:
                continue

            FileInformation = await iamagesdb.fetch_one("SELECT FileDescription, FileNSFW, FilePrivate, FileMime, FileWidth, FileHeight, FileCreatedDate, FileLink, FileExcludeSearch FROM Files WHERE FileID = :FileID", {
                "FileID": FileID
            })

            if not FileInformation:
                continue

            FilePrivate = bool(FileInformation[2])

            if FilePrivate:
                if not UserID or FileID != await SharedFunctions.check_file_belongs(FileID, UserID):
                    continue

            response_body_item = {
                "FileID": None,
                "FileDescription": None,
                "FileNSFW": None,
                "FilePrivate": None,
                "FileMime": None,
                "FileWidth": None,
                "FileHeight": None,
                "FileCreatedDate": None,
                "FileExcludeSearch": None
            }

            response_body_item["FileID"] = FileID
            response_body_item["FileDescription"] = FileInformation[0]
            response_body_item["FileNSFW"] = bool(FileInformation[1])
            response_body_item["FilePrivate"] = FilePrivate

            if FileInformation[7]:
                linked_FileInformation = await iamagesdb.fetch_one("SELECT FileMime, FileWidth, FileHeight FROM Files WHERE FileID = :FileID", {
                    "FileID": FileInformation[7]
                })
                response_body_item["FileMime"] = linked_FileInformation[0]
                response_body_item["FileWidth"] = linked_FileInformation[1]
                response_body_item["FileHeight"] = linked_FileInformation[2]
            else:
                response_body_item["FileMime"] = FileInformation[3]
                response_body_item["FileWidth"] = FileInformation[4]
                response_body_item["FileHeight"] = FileInformation[5]

            response_body_item["FileCreatedDate"] = FileInformation[6]
            response_body_item["FileExcludeSearch"] = bool(FileInformation[8])

            response_body.append(response_body_item)
            processed_FileIDs.append(FileID)
        
        return starlette.responses.JSONResponse(response_body)


class Embed(starlette.endpoints.HTTPEndpoint):
    async def get(self, request):
        response_template = {
            "request": request,
            "title": "Untitled - from Iamages",
            "FileDescription": "Untitled",
            "FileID": 0,
            "FileMime": "",
            "FileWidth": 0,
            "FileHeight": 0
        }

        FileID = int(request.path_params["FileID"])
        FileInformation = await iamagesdb.fetch_one("SELECT FileDescription, FilePrivate, FileMime, FileWidth, FileHeight, FileLink From Files WHERE FileID = :FileID", {
            "FileID": FileID
        })

        response_status_code = 200

        await request.send_push_promise("/private/static/css/bulma.min.css")

        if not FileInformation:
            response_template["title"] = "File not found on Iamages"
            response_template["FileDescription"] = "The requested file couldn't be found. Ran memcheck yet? 🐿"
            return templates.TemplateResponse("embed.html", response_template, status_code=404)

        if bool(FileInformation[1]):
            response_template["title"] = "Private file from Iamages"
            response_template["FileDescription"] = "The owner of this file has enabled private mode. No peeking allowed! 👀"
            response_status_code = 401
        else:
            response_template["title"] = FileInformation[0] + " - from Iamages"
            response_template["FileDescription"] = FileInformation[0]
            response_template["FileID"] = FileID
            if FileInformation[5]:
                linked_FileInformation = await iamagesdb.fetch_one("SELECT FileMime, FileWidth, FileHeight FROM Files WHERE FileID = :FileID", {
                    "FileID": FileInformation[5]
                })
                response_template["FileMime"] = linked_FileInformation[0]
                response_template["FileWidth"] = linked_FileInformation[1]
                response_template["FileHeight"] = linked_FileInformation[2]
            else:
                response_template["FileMime"] = FileInformation[2]
                response_template["FileWidth"] = FileInformation[3]
                response_template["FileHeight"] = FileInformation[4]

        return templates.TemplateResponse("embed.html", response_template, status_code=response_status_code)


class Img(starlette.endpoints.HTTPEndpoint):
    async def get(self, request):
        FileID = int(request.path_params["FileID"])
        FileInformation = await iamagesdb.fetch_one("SELECT FileName, FilePrivate, FileMime, FileLink FROM Files WHERE FileID = :FileID", {
            "FileID": FileID
        })

        if not FileInformation:
            raise starlette.exceptions.HTTPException(404)

        if not bool(FileInformation[1]):
            return await self.send_img(FileID, FileInformation)

        UserID = await SharedFunctions.process_auth_header(request.headers)
        if not UserID or FileID != await SharedFunctions.check_file_belongs(FileID, UserID):
            raise starlette.exceptions.HTTPException(401)

        return await self.send_img(FileID, FileInformation)


    async def send_img(self, FileID, FileInformation):
        FileID = str(FileID)
        FileName = FileInformation[0]
        FileMime = FileInformation[2]

        if FileInformation[3]:
            linked_FileInformation = await iamagesdb.fetch_one("SELECT FileName, FileMime FROM Files WHERE FileID = :FileID", {
                "FileID": FileInformation[3]
            })
            FileID = str(FileInformation[3])
            FileName = linked_FileInformation[0]
            FileMime = linked_FileInformation[1]

        file_path = os.path.join(FILES_PATH, FileID, FileName)

        if not os.path.isfile(file_path):
            raise starlette.exceptions.HTTPException(404)

        return starlette.responses.FileResponse(file_path, media_type=FileMime)


class Thumb(starlette.endpoints.HTTPEndpoint):
    async def get(self, request):
        FileID = int(request.path_params["FileID"])
        FileInformation = await iamagesdb.fetch_one("SELECT FileName, FilePrivate, FileMime, FileLink FROM Files WHERE FileID = :FileID", {
            "FileID": FileID
        })

        if not FileInformation:
            raise starlette.exceptions.HTTPException(404)

        if not bool(FileInformation[1]):
            return await self.send_thumb(FileID, FileInformation, request)

        UserID = await SharedFunctions.process_auth_header(request.headers)
        if not UserID or FileID != await SharedFunctions.check_file_belongs(FileID, UserID):
            raise starlette.exceptions.HTTPException(401)

        return await self.send_thumb(FileID, FileInformation, request)

    async def send_thumb(self, FileID, FileInformation, request):
        FileID = str(FileID)
        FileName = FileInformation[0]
        FileMime = FileInformation[2]

        if FileInformation[3]:
            linked_FileInformation = await iamagesdb.fetch_one("SELECT FileName, FileMime FROM Files WHERE FileID = :FileID", {
                "FileID": FileInformation[3]
            })
            FileID = str(FileInformation[3])
            FileName = linked_FileInformation[0]
            FileMime = linked_FileInformation[1]

        thumb_path = os.path.join(THUMBS_PATH, FileID, FileName)

        if not os.path.isfile(thumb_path):
            bg_task = starlette.background.BackgroundTask(SharedFunctions.create_thumb, FileID=FileID, FileName=FileName, FileMime=FileMime)
            return starlette.responses.RedirectResponse(request.url_for("img", FileID=FileID), background=bg_task)
        
        return starlette.responses.FileResponse(thumb_path, media_type=FileMime)


class Search(starlette.endpoints.HTTPEndpoint):
    async def post(self, request):
        request_body = await SharedFunctions.parse_request_json(request)

        if "FileDescription" not in request_body or type(request_body["FileDescription"]) != str:
            raise starlette.exceptions.HTTPException(400)

        UserID = None

        if "UserName" in request_body and "UserPassword" in request_body:
            UserID = await SharedFunctions.check_user(request_body["UserName"], request_body["UserPassword"])

        FileIDs = await iamagesdb.fetch_all("SELECT FileID, FilePrivate FROM Files WHERE instr(FileDescription, :FileDescription) > 0 AND FileExcludeSearch = 0", {
            "FileDescription": request_body["FileDescription"]
        })

        response_body = {
            "FileDescription": "",
            "FileIDs": []
        }

        response_body["FileDescription"] = request_body["FileDescription"]

        for FileID in FileIDs:
            if not bool(FileID[1]):
                response_body["FileIDs"].append(FileID[0])
            else:
                if not UserID:
                    continue
                if not await SharedFunctions.check_file_belongs(FileID[0], UserID):
                    continue
                response_body["FileIDs"].append(FileID[0])

        return starlette.responses.JSONResponse(response_body)


class User:
    class Info(starlette.endpoints.HTTPEndpoint):
        async def post(self, request):
            request_body = await SharedFunctions.parse_request_json(request)

            if "UserName" not in request_body or type(request_body["UserName"]) != str:
                raise starlette.exceptions.HTTPException(400)

            UserInformation = await iamagesdb.fetch_one("SELECT UserBiography, UserCreatedDate FROM Users WHERE UserName = :UserName", {
                "UserName": request_body["UserName"]
            })

            if not UserInformation:
                raise starlette.exceptions.HTTPException(404)

            response_body = {
                "UserName": None,
                "UserInfo": {}
            }

            response_body["UserName"] = request_body["UserName"]
            response_body["UserInfo"]["UserBiography"] = UserInformation[0]
            response_body["UserInfo"]["UserCreatedDate"] = UserInformation[1]

            return starlette.responses.JSONResponse(response_body)


    class Files(starlette.endpoints.HTTPEndpoint):
        async def post(self, request):
            request_body = await SharedFunctions.parse_request_json(request)

            if "UserName" not in request_body or "UserPassword" not in request_body or type(request_body["UserName"]) != str or type(request_body["UserPassword"]) != str:
                raise starlette.exceptions.HTTPException(400)

            UserID = await SharedFunctions.check_user(request_body["UserName"], request_body["UserPassword"])

            if not UserID:
                raise starlette.exceptions.HTTPException(401)

            response_body = {
                "UserName": None,
                "FileIDs": []
            }

            response_body["UserName"] = request_body["UserName"]
            FileIDs = await iamagesdb.fetch_all("SELECT FileID FROM Files_Users WHERE UserID = :UserID ORDER BY FileID DESC", {
                "UserID": UserID
            })
            for FileID in FileIDs:
                response_body["FileIDs"].append(FileID[0])
            return starlette.responses.JSONResponse(response_body)


    class Modify(starlette.endpoints.HTTPEndpoint):
        async def patch(self, request):
            request_body = await SharedFunctions.parse_request_json(request)

            if "UserName" not in request_body or "UserPassword" not in request_body or "Modifications" not in request_body or type(request_body["UserName"]) != str or type(request_body["UserPassword"]) != str or type(request_body["Modifications"]) != dict:
                raise starlette.exceptions.HTTPException(400)

            UserID = await SharedFunctions.check_user(request_body["UserName"], request_body["UserPassword"])

            if not UserID:
                raise starlette.exceptions.HTTPException(401)

            basic_query = "UPDATE Users SET {0} = :value WHERE UserID = " + str(UserID)

            response_body = {
                "UserName": None,
                "Modifications": []
            }

            response_body["UserName"] = request_body["UserName"]

            for modification in request_body["Modifications"]:
                if modification in ["UserBiography"]:
                    modification_query = basic_query.format(modification)
                    await iamagesdb.execute(modification_query, {
                        "value": request_body["Modifications"][modification]
                    })
                elif modification == "UserPassword":
                    basic_query = basic_query.format(modification)
                    await iamagesdb.execute(basic_query, {
                        "value": bcrypt.hashpw(bytes(request_body["Modifications"][modification], 'utf-8'), bcrypt.gensalt())
                    })
                elif modification == "DeleteUser":
                    await iamagesdb.execute("DELETE FROM Users WHERE UserID = :UserID", {
                        "UserID": UserID
                    })
                    FileIDs = await iamagesdb.fetch_all("SELECT FileID FROM Files_Users WHERE UserID = :UserID", {
                        "UserID": UserID
                    })
                    for FileID in FileIDs:
                        await SharedFunctions.delete_file(FileID[0])
                response_body["Modifications"].append(modification)

            return starlette.responses.JSONResponse(response_body)


    class New(starlette.endpoints.HTTPEndpoint):
        async def put(self, request):
            request_body = await SharedFunctions.parse_request_json(request)

            if "UserName" not in request_body or "UserPassword" not in request_body or type(request_body["UserName"]) != str or type(request_body["UserPassword"]) != str:
                raise starlette.exceptions.HTTPException(400)

            if await SharedFunctions.check_user(request_body["UserName"], request_body["UserPassword"]):
                raise starlette.exceptions.HTTPException(403)

            await iamagesdb.execute("INSERT INTO Users (UserName, UserPassword, UserCreatedDate) VALUES (:UserName, :UserPassword, datetime('now'))", {
                "UserName": request_body["UserName"],
                "UserPassword": bcrypt.hashpw(bytes(request_body["UserPassword"], 'utf-8'), bcrypt.gensalt())
            })

            response_body = {
                "UserName": None
            }

            response_body["UserName"] = request_body["UserName"]

            return starlette.responses.JSONResponse(response_body)
    

    class Check(starlette.endpoints.HTTPEndpoint):
        async def post(self, request):
            request_body = await SharedFunctions.parse_request_json(request)

            if "UserName" not in request_body or "UserPassword" not in request_body or type(request_body["UserName"]) != str or type(request_body["UserPassword"]) != str:
                raise starlette.exceptions.HTTPException(400)

            if not await SharedFunctions.check_user(request_body["UserName"], request_body["UserPassword"]):
                raise starlette.exceptions.HTTPException(401)

            response_body = {
                "UserName": None
            }

            response_body["UserName"] = request_body["UserName"]

            return starlette.responses.JSONResponse(response_body)                
                

app = starlette.applications.Starlette(routes=[
    starlette.routing.Mount("/iamages/api", routes=[
        starlette.routing.Mount("/private", routes=[
            starlette.routing.Mount("/static", starlette.staticfiles.StaticFiles(directory=os.path.join(IAMAGES_PATH, "static")), name="static"),
            starlette.routing.Route("/tos", Private.TOS),
            starlette.routing.Route("/privacy", Private.PrivacyPolicy)
        ]),
        starlette.routing.Route("/", Docs),
        starlette.routing.Route("/latest", Latest),
        starlette.routing.Route("/random", Random),
        starlette.routing.Route("/upload", Upload),
        starlette.routing.Route("/modify", Modify),
        starlette.routing.Route("/info/{FileID:int}", Info, name="info"),
        starlette.routing.Route("/infos", Infos),
        starlette.routing.Route("/embed/{FileID:int}", Embed, name="embed"),
        starlette.routing.Route("/img/{FileID:int}", Img, name="img"),
        starlette.routing.Route("/thumb/{FileID:int}", Thumb, name="thumb"),
        starlette.routing.Route("/search", Search),
        starlette.routing.Mount("/user", routes=[
            starlette.routing.Route("/info", User.Info),
            starlette.routing.Route("/files", User.Files),
            starlette.routing.Route("/modify", User.Modify),
            starlette.routing.Route("/new", User.New),
            starlette.routing.Route("/check", User.Check)
        ])
    ])
], middleware=[
    starlette.middleware.Middleware(starlette.middleware.cors.CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]),
    starlette.middleware.Middleware(starlette.middleware.gzip.GZipMiddleware)
], on_startup=[iamagesdb.connect], on_shutdown=[iamagesdb.disconnect])
