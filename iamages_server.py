__version__ = "2.0.0"
__copyright__ = "© jkelol111 et al 2020-present"

import os
import json
import databases
import shutil
import random
import bcrypt
import base64
import hashlib
import magic
import string
import mimetypes
import PIL.Image
import starlette.applications
import starlette.endpoints
import starlette.routing
import starlette.staticfiles
import starlette.templating
import starlette.middleware
import starlette.middleware.cors
import starlette.middleware.gzip
import starlette.responses

IAMAGES_PATH = os.path.dirname(os.path.realpath(__file__))

server_config = json.load(open("servercfg.json", "r"))

if not os.path.isdir(server_config["files"]["storage"]["directory"]):
    os.makedirs(server_config["files"]["storage"]["directory"])

IAMAGESDB_PATH = os.path.join(server_config["files"]["storage"]["directory"], "iamages.db")
iamagesdb = databases.Database("sqlite:///" + IAMAGESDB_PATH)

FILES_PATH = os.path.join(server_config["files"]["storage"]["directory"], "files")
if not os.path.isdir(FILES_PATH):
    os.makedirs(FILES_PATH)

templates = starlette.templating.Jinja2Templates(directory=os.path.join(IAMAGES_PATH, "templates"))

class SharedFunctions:
    @staticmethod
    async def delete_file(FileID: int):
        ex_file_directory = os.path.join(FILES_PATH, str(FileID))
        file_links = await iamagesdb.fetch_all("SELECT FileID FROM Files WHERE FileLink = :FileID", {
            "FileID": FileID
        })
        if file_links:
            ex_file_info = await iamagesdb.fetch_one("SELECT FileName, FileMime, FileWidth, FileHeight, FileHash FROM Files WHERE FileID = :FileID", {
                "FileID": FileID
            })
            new_file_directory = os.path.join(FILES_PATH, str(file_links[0][0]))
            if not os.path.isdir(new_file_directory):
                os.makedirs(new_file_directory)
            new_file_name = ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(6)) + mimetypes.guess_extension(ex_file_info[1])
            with open(os.path.join(ex_file_directory, ex_file_info[0]), "rb") as ex_file:
                with open(os.path.join(new_file_directory, new_file_name), "wb") as new_file:
                    new_file.write(ex_file.read())
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
        await iamagesdb.execute("DELETE FROM Files WHERE FileID = :FileID", {
            "FileID": FileID
        })
        await iamagesdb.execute("DELETE FROM Files_Users WHERE FileID = :FileID", {
            "FileID": FileID
        })

    @staticmethod
    async def check_user(UserName: str, UserPassword: str):
        users = await iamagesdb.fetch_all("SELECT UserID, UserPassword FROM Users WHERE UserName = :UserName", {
            "UserName": UserName
        })
        if users:
            for user in users:
                if bcrypt.checkpw(bytes(UserPassword, "utf-8"), user[1]):
                    return user[0]
            return None
        else:
            return None

    @staticmethod
    async def check_file_belongs(FileID: int, UserID: int):
        if FileID == await iamagesdb.fetch_val("SELECT FileID FROM Files_Users WHERE FileID = :FileID AND UserID = :UserID", {
            "FileID": FileID,
            "UserID": UserID
        }):
            return FileID
        else:
            return None

    @staticmethod
    async def process_auth_header(headers: list):
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


class Private:
    class TOS(starlette.endpoints.HTTPEndpoint):
        async def get(self, request):
            return templates.TemplateResponse("tos.html", {
                "request": request,
                "owner": server_config["meta"]["owner"]
            })

    class PrivacyPolicy(starlette.endpoints.HTTPEndpoint):
        async def get(self, request):
            return templates.TemplateResponse("privacy.html", {
                "request": request,
                "owner": server_config["meta"]["owner"]
            })

class Docs(starlette.endpoints.HTTPEndpoint):
    async def get(self, request):
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
        FileIDs = await iamagesdb.fetch_all("SELECT FileID FROM Files WHERE FilePrivate = 0 ORDER BY FileID DESC LIMIT 10")
        for FileID in FileIDs:
            response_body["FileIDs"].append(FileID[0])
        return starlette.responses.JSONResponse(response_body)

class Random(starlette.endpoints.HTTPEndpoint):
    async def get(self, request):
        total_files = await iamagesdb.fetch_val("SELECT COUNT(FileID) FROM Files")
        if total_files > 1:
            successful_FileID = 0
            attempts = 0
            while successful_FileID == 0 and attempts <= 3:
                successful_FileID = random.randint(1, total_files)
                actual_successful_FileID = await iamagesdb.fetch_one("SELECT FileID From Files WHERE FileID = :FileID AND FilePrivate = 0", {
                    "FileID": successful_FileID
                })
                if not actual_successful_FileID:
                    successful_FileID = 0
                    attempts += 1
            if successful_FileID != 0:
                return starlette.responses.RedirectResponse(request.url_for("info", FileID=successful_FileID))
            else:
                return starlette.responses.Response(status_code=503)
        else:
            return starlette.responses.Response(status_code=503)

class Upload(starlette.endpoints.HTTPEndpoint):
    async def put(self, request):
        request_body = await request.json()
        response_body = {
            "FileID": None
        }
        if "FileData" in request_body and "FileNSFW" in request_body and "FileDescription" in request_body:
            UserID = None
            if "UserName" in request_body and "UserPassword" in request_body:
                UserID = await SharedFunctions.check_user(request_body["UserName"], request_body["UserPassword"])
                if not UserID:
                    return starlette.responses.Response(status_code=401)
            if ((len(request_body["FileData"]) * 3) / 4) < server_config["files"]["max_size"]:
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
                        if "FilePrivate" in request_body:
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
                    response_body["FileID"] = FileID
                    return starlette.responses.JSONResponse(response_body)
                else:
                    file_folder_path = os.path.join(FILES_PATH, str(FileID))
                    if not os.path.isdir(file_folder_path):
                        os.makedirs(file_folder_path)
                    file_path = os.path.join(file_folder_path, "unprocessed.image")
                    with open(file_path, "wb") as file:
                        file.write(FileData)
                    FileMime = magic.from_file(file_path, mime=True)
                    if FileMime in server_config["files"]["accept_filemimes"]:
                        random_file_name = ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(6)) + mimetypes.guess_extension(FileMime)
                        new_file_path = os.path.join(file_folder_path, random_file_name)
                        with PIL.Image.open(file_path) as img:
                            if FileMime == "image/gif":
                                img.save(new_file_path, save_all=True)
                            else:
                                img.save(new_file_path)
                            await iamagesdb.execute("UPDATE Files SET FileName = :FileName, FileWidth = :FileWidth, FileHeight = :FileHeight, FileMime = :FileMime, FileHash = :FileHash WHERE FileID = :FileID", {
                                "FileName": random_file_name,
                                "FileWidth": img.size[0],
                                "FileHeight": img.size[1],
                                "FileMime": FileMime,
                                "FileHash": FileHash,
                                "FileID": FileID
                            })
                        os.remove(file_path)
                        if UserID:
                            await iamagesdb.execute("INSERT INTO Files_Users (FileID, UserID) VALUES (:FileID, :UserID)", {
                                "FileID": FileID,
                                "UserID": UserID
                            })
                            if "FilePrivate" in request_body:
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
                    else:
                        await SharedFunctions.delete_file(FileID)
                        return starlette.responses.Response(status_code=415)
                    response_body["FileID"] = FileID
                    return starlette.responses.JSONResponse(response_body)
            else:
                return starlette.responses.Response(status_code=413)
        else:
            return starlette.responses.Response(status_code=400)

class Modify(starlette.endpoints.HTTPEndpoint):
    async def patch(self, request):
        request_body = await request.json()
        response_body = {
            "FileID": None,
            "Modifications": []
        }
        if "UserName" in request_body and "UserPassword" in request_body and "FileID" in request_body and "Modifications" in request_body:
            UserID = await SharedFunctions.check_user(request_body["UserName"], request_body["UserPassword"])
            if UserID:
                FileID = await SharedFunctions.check_file_belongs(request_body["FileID"], UserID)
                if FileID == request_body["FileID"]:
                    basic_query = "UPDATE Files SET {0} = :value WHERE FileID = " + str(FileID)
                    for modification in request_body["Modifications"]:
                        if modification in ["FileDescription", "FileNSFW", "FilePrivate"]:
                            basic_query = basic_query.format(modification)
                            await iamagesdb.execute(basic_query, {
                                "value": request_body["Modifications"][modification]
                            })
                        elif modification == "DeleteFile":
                            await SharedFunctions.delete_file(FileID)
                        response_body["Modifications"].append(modification)
                    response_body["FileID"] = FileID
                    return starlette.responses.JSONResponse(response_body)
                else:
                    return starlette.responses.Response(status_code=404)
            else:
                return starlette.responses.Response(status_code=401)
        else:
            return starlette.responses.Response(status_code=400)

class Info(starlette.endpoints.HTTPEndpoint):
    async def get(self, request):
        response_body = {
            "FileID": None,
            "FileDescription": None,
            "FileNSFW": None,
            "FilePrivate": None,
            "FileMime": None,
            "FileWidth": None,
            "FileHeight": None,
            "FileCreatedDate": None
        }
        async def set_response(FileInformation):
            response_body["FileID"] = int(request.path_params["FileID"])
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

        FileID = int(request.path_params["FileID"])
        FileInformation = await iamagesdb.fetch_one("SELECT FileDescription, FileNSFW, FilePrivate, FileMime, FileWidth, FileHeight, FileCreatedDate, FileLink FROM Files WHERE FileID = :FileID", {
            "FileID": FileID
        })
        FilePrivate =  bool(FileInformation[2])
        if FilePrivate:
            UserID = await SharedFunctions.process_auth_header(request.headers)
            if UserID:
                if FileID == await SharedFunctions.check_file_belongs(FileID, UserID):
                    await set_response(FileInformation)
                else:
                    return starlette.responses.Response(status_code=401)
            else:
                return starlette.responses.Response(status_code=403)
        else:
            await set_response(FileInformation)
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
        if FileInformation:
            if bool(FileInformation[1]):
                response_template["title"] = "Private file from Iamages"
                response_template["FileDescription"] = "The owner of this file has enabled private mode. No peeking allowed! 👀"
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
            return templates.TemplateResponse("embed.html", response_template)
        else:
            response_template["title"] = "File not found on Iamages"
            response_template["FileDescription"] = "The requested file couldn't be found. Ran memcheck yet? 🐿"
            return templates.TemplateResponse("embed.html", response_template, status_code=404)

class Img(starlette.endpoints.HTTPEndpoint):
    async def get(self, request):
        FileID = int(request.path_params["FileID"])
        FileInformation = await iamagesdb.fetch_one("SELECT FileName, FilePrivate, FileMime, FileLink FROM Files WHERE FileID = :FileID", {
            "FileID": FileID
        })

        async def send_img():
            FileMime = FileInformation[2]
            if FileInformation[3]:
                linked_FileInformation = await iamagesdb.fetch_one("SELECT FileName, FileMime FROM Files WHERE FileID = :FileID", {
                    "FileID": FileInformation[3]
                })
                file_path = os.path.join(FILES_PATH, str(FileInformation[3]), linked_FileInformation[0])
                FileMime = linked_FileInformation[1]
            else:
                file_path = os.path.join(FILES_PATH, str(FileID), FileInformation[0])
            
            if os.path.isfile(file_path):
                with open(file_path, "rb") as file:
                    return starlette.responses.Response(file.read(), headers={
                        "Content-Type": FileMime
                    })
            else:
                return starlette.responses.Response(status_code=404)

        if FileInformation:
            if FileInformation[1]:
                UserID = await SharedFunctions.process_auth_header(request.headers)
                if UserID:
                    if FileID == await SharedFunctions.check_file_belongs(FileID, UserID):
                        return await send_img()
                    else:
                        return starlette.responses.Response(status_code=401)
                else:
                    return starlette.responses.Response(status_code=401)
            else:
                return await send_img()
        else:
            return starlette.responses.Response(status_code=404)

class User:
    class Info(starlette.endpoints.HTTPEndpoint):
        async def post(self, request):
            request_body = await request.json()
            response_body = {
                "UserName": None,
                "UserInfo": {}
            }
            if "UserName" in request_body and "UserPassword" in request_body:
                UserID = await SharedFunctions.check_user(request_body["UserName"], request_body["UserPassword"])
                if UserID:
                    UserInfo = await iamagesdb.fetch_one("SELECT UserBiography, UserCreatedDate FROM Users WHERE UserID = :UserID", {
                        "UserID": UserID
                    })
                    if UserInfo:
                        response_body["UserName"] = request_body["UserName"]
                        response_body["UserInfo"]["UserBiography"] = UserInfo[0]
                        response_body["UserInfo"]["UserCreatedDate"] = UserInfo[1]
                        return starlette.responses.JSONResponse(response_body)
                else:
                    return starlette.responses.Response(status_code=401)
            else:
                return starlette.responses.Response(status_code=400)

    class Files(starlette.endpoints.HTTPEndpoint):
        async def post(self, request):
            request_body = await request.json()
            response_body = {
                "UserName": None,
                "FileIDs": []
            }
            if "UserName" in request_body and "UserPassword" in request_body:
                UserID = await SharedFunctions.check_user(request_body["UserName"], request_body["UserPassword"])
                if UserID:
                    response_body["UserName"] = request_body["UserName"]
                    FileIDs = await iamagesdb.fetch_all("SELECT FileID FROM Files_Users WHERE UserID = :UserID ORDER BY FileID DESC", {
                        "UserID": UserID
                    })
                    for FileID in FileIDs:
                        response_body["FileIDs"].append(FileID[0])
                    return starlette.responses.JSONResponse(response_body)
                else:
                    return starlette.responses.Response(status_code=401)
            else:
                return starlette.responses.Response(status_code=400)

    class Modify(starlette.endpoints.HTTPEndpoint):
        async def patch(self, request):
            request_body = await request.json()
            response_body = {
                "UserName": None,
                "Modifications": []
            }
            if "UserName" in request_body and "UserPassword" in request_body and "Modifications" in request_body:
                UserID = await SharedFunctions.check_user(request_body["UserName"], request_body["UserPassword"])
                if UserID:
                    basic_query = "UPDATE Users SET {0} = :value WHERE UserID = " + str(UserID)
                    for modification in request_body["Modifications"]:
                        if modification in ["UserBiography", "UserName"]:
                            basic_query = basic_query.format(modification)
                            await iamagesdb.execute(basic_query, {
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
                    response_body["UserName"] = request_body["UserName"]
                    return starlette.responses.JSONResponse(response_body)
                else:
                    return starlette.responses.Response(status_code=401)
            else:
                return starlette.responses.Response(status_code=400)

    class New(starlette.endpoints.HTTPEndpoint):
        async def put(self, request):
            request_body = await request.json()
            response_body = {
                "UserName": None
            }
            if "UserName" in request_body and "UserPassword" in request_body:
                if await iamagesdb.fetch_one("SELECT UserID FROM Users WHERE UserName = :UserName", {
                    "UserName": request_body["UserName"]
                }):
                    return starlette.responses.JSONResponse(response_body, status_code=403)
                else:
                    await iamagesdb.execute("INSERT INTO Users (UserName, UserPassword, UserCreatedDate) VALUES (:UserName, :UserPassword, datetime('now'))", {
                        "UserName": request_body["UserName"],
                        "UserPassword": bcrypt.hashpw(bytes(request_body["UserPassword"], 'utf-8'), bcrypt.gensalt())
                    })
                    response_body["UserName"] = request_body["UserName"]
                    return starlette.responses.JSONResponse(response_body)
            else:
                return starlette.responses.Response(status_code=400)
    
    class Check(starlette.endpoints.HTTPEndpoint):
        async def post(self, request):
            request_body = await request.json()
            response_body = {
                "UserName": None
            }
            if "UserName" in request_body and "UserPassword" in request_body:
                if await SharedFunctions.check_user(request_body["UserName"], request_body["UserPassword"]):
                    response_body["UserName"] = request_body["UserName"]
                    return starlette.responses.JSONResponse(response_body)
                else:
                    return starlette.responses.Response(status_code=401)
            else:
                return starlette.responses.Response(status_code=400)

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
        starlette.routing.Route("/embed/{FileID:int}", Embed, name="embed"),
        starlette.routing.Route("/img/{FileID:int}", Img, name="img"),
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
