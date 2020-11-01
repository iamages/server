__version__ = "master"
__copyright__ = "© jkelol111 et al 2020-present"

import base64
from pysqlcipher3 import dbapi2 as sqlite3
# import sqlite3
import json
import os
import getpass
import argparse
import logging
import bcrypt
import ssl
import magic
import random
import string
import mimetypes
import shutil
from PIL import Image
import tornado.web
import tornado.escape
import tornado.ioloop

argument_parser = argparse.ArgumentParser(description="Iamages Server")
argument_parser.add_argument("config_path", metavar="config_path", type=str, help="The path to the server's JSON configuration file.")
arguments = argument_parser.parse_args()

logging.basicConfig(format='SERVER | %(asctime)s | %(levelname)s | %(message)s', datefmt='%d/%m/%y %H:%M:%S', level=logging.INFO)

IAMAGES_PATH = os.path.dirname(os.path.realpath(__file__))
logging.info("[Iamages API Server version '{0}']".format(__version__))
logging.info(__copyright__)
logging.info("IAMAGES_PATH = " + str(IAMAGES_PATH))

logging.info("Starting imgcloud server...")
logging.info("Loading server configuration file...")
try:
    server_config = json.load(open(os.path.join(os.getcwd(), arguments.config_path), "r"))
    logging.info("Loaded server configuration file!")
except Exception:
    logging.exception("Server config load failed! Halting...", exc_info=True)
    exit()

if not os.path.isdir(server_config["storage_directory"]):
    os.makedirs(server_config["storage_directory"])

FILESDB_PATH = os.path.join(server_config["storage_directory"], "store.db")

logging.info("Connecting to storage database...")
storedb_connection = sqlite3.connect(FILESDB_PATH, )
storedb_cursor = storedb_connection.cursor()

try:
    empty = storedb_cursor.execute("SELECT name FROM sqlite_master").fetchall()

    if empty == []:
        logging.info("Storage database is new, creating tables...")
        storedb_cursor.execute("PRAGMA key = 'temppassword123'")
        with open(os.path.join(IAMAGES_PATH, "store.sql"), "r") as query:
            storedb_cursor.executescript(query.read())
        pwd = [
            getpass.getpass("Input new database password (input will not show): "),
            getpass.getpass("Re-enter new database password (input will not show): ")
        ]
        if pwd[0] == pwd[1]:
            storedb_cursor.execute("PRAGMA rekey = {0}".format(pwd[1]))
        else:
            logging.critical("Newly inputted passwords do not match! Removing database and halting...")
            if os.path.isfile(FILESDB_PATH):
                os.remove(FILESDB_PATH)
            exit()
    else:
        logging.warning("Database seems strange... halting!")
        exit()
except:
    storedb_cursor.execute("PRAGMA key = {0}".format(getpass.getpass("Input database password (input will not show): ")))
    try:
        storedb_cursor.execute("SELECT name FROM sqlite_master").fetchall()
    except:
        logging.error("The inputted password is incorrect! Halting...")
        exit()
        
logging.info("Connected to storage database!")

FILES_PATH = os.path.join(server_config["storage_directory"], "files")

if not os.path.isdir(FILES_PATH):
    os.makedirs(FILES_PATH)

def check_user(UserName, UserPassword):
    users = storedb_cursor.execute("SELECT UserID, UserPassword FROM Users WHERE UserName = ?", (UserName,)).fetchall()
    if users:
        for user in users:
            if bcrypt.checkpw(bytes(UserPassword, "utf-8"), user[1]):
                return user[0]
        return None
    else:
        return None

def delete_file(FileID):
    folderpath = os.path.join(FILES_PATH, str(FileID))
    if os.path.isdir(folderpath):
        shutil.rmtree(folderpath)
    storedb_cursor.execute("DELETE FROM Files WHERE FileID = ?", (FileID,))
    storedb_cursor.execute("DELETE FROM Files_Users WHERE FileID = ?", (FileID,))

def check_private_file(FileID, UserID):
    if int(FileID) == storedb_cursor.execute("SELECT Files.FileID FROM Files INNER JOIN Files_Users ON Files.FileID = Files_Users.FileID WHERE Files_Users.FileID = ? AND Files_Users.UserID = ?", (FileID, UserID)).fetchone()[0]:
        return FileID
    else:
        return None

class RootInfoHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("api-doc.html", instance_owner_name=server_config["instance_owner"]["name"], instance_owner_contact=server_config["instance_owner"]["contact"])

class TOSHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("tos.html", instance_owner_name=server_config["instance_owner"]["name"], instance_owner_contact=server_config["instance_owner"]["contact"])

class PrivacyPolicyHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("privacy.html")

class LatestFilesHandler(tornado.web.RequestHandler):
    def get(self):
        response = {
            "FileIDs": []
        }
        files = storedb_cursor.execute("SELECT FileID FROM Files WHERE FilePrivate = 0 ORDER BY FileID DESC LIMIT 10").fetchall()
        for file in files:
            response["FileIDs"].append(file[0])
        self.write(response)

class RandomFileHandler(tornado.web.RequestHandler):
    def get(self):
        total_FileIDs = storedb_cursor.execute("SELECT COUNT(*) FROM Files").fetchone()[0]
        if total_FileIDs > 1:
            successful_FileID = 0
            tries = 0
            while successful_FileID == 0 or tries <= 3:
                successful_FileID = random.randint(1, total_FileIDs)
                if not storedb_cursor.execute("SELECT FileID From Files WHERE FileID = ? AND FilePrivate = 0", (successful_FileID,)).fetchone():
                    successful_FileID = 0
                    tries += 1
            if successful_FileID != 0:
                self.redirect("/iamages/api/info/" + str(successful_FileID))
            else:
                self.send_error(503)
        else:
            self.send_error(503)

class FileUploadHandler(tornado.web.RequestHandler):
    def put(self):
        request = tornado.escape.json_decode(self.request.body)
        response = {
            "FileID": None
        }

        UserID = None

        def handle_upload():
            if ((len(request["FileData"]) * 3) / 4 < server_config["max_file_size"]):
                storedb_cursor.execute("INSERT INTO Files (FileDescription, FileNSFW, FileCreatedDate) VALUES (?, ?, datetime('now'))", (request["FileDescription"], request["FileNSFW"]))
                FileID = storedb_cursor.execute("SELECT FileID FROM Files ORDER BY FileID DESC").fetchone()[0]
                folderpath = os.path.join(FILES_PATH, str(FileID))
                if not os.path.isdir(folderpath):
                    os.makedirs(folderpath)
                filepath = os.path.join(folderpath, "unprocessed.image")
                with open(filepath, "wb") as file:
                    file.write(base64.b64decode(request["FileData"]))
                FileMime = magic.from_file(filepath, mime=True)
                if FileMime in ["image/jpeg", "image/png", "image/gif"]:
                    storedb_cursor.execute("UPDATE Files SET FileMime = ? WHERE FileID = ?", (FileMime, FileID))
                    random_filename = ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(6)) + mimetypes.guess_extension(FileMime)
                    new_filepath = os.path.join(folderpath, random_filename)
                    with Image.open(filepath) as img:
                        storedb_cursor.execute("UPDATE Files SET FileName = ?, FileWidth = ?, FileHeight = ? WHERE FileID = ?", (random_filename, img.size[0], img.size[1], FileID))
                        if FileMime == "image/gif":
                            img.save(new_filepath, save_all=True)
                        else:
                            img.save(new_filepath)
                    os.remove(filepath)
                    if UserID:
                        storedb_cursor.execute("INSERT INTO Files_Users (FileID, UserID) VALUES (?, ?)", (FileID, UserID))
                        if "FilePrivate" in request:
                            storedb_cursor.execute("UPDATE Files SET FilePrivate = ? WHERE FileID = ?", (request["FilePrivate"], FileID))
                        else:
                            storedb_cursor.execute("UPDATE Files SET FilePrivate = ? WHERE FileID = ?", (False, FileID))
                    else:
                        storedb_cursor.execute("UPDATE Files SET FilePrivate = ? WHERE FileID = ?", (False, FileID))
                else:
                    delete_file(FileID)
                    self.set_status(415)
                    FileID = None
                storedb_connection.commit()
                response["FileID"] = FileID
                self.write(response)
            else:
                self.set_status(413)
                self.write(response)

        if "FileData" in request and "FileNSFW" in request and "FileDescription" in request:
            if "UserName" in request and "UserPassword" in request:
                UserID = check_user(request["UserName"], request["UserPassword"])
                if UserID:
                    handle_upload()
                else:
                    self.set_status(401)
                    self.write(response)
            else:
                handle_upload()
        else:
            self.set_status(400)
            self.write(response)

class FileModifyHandler(tornado.web.RequestHandler):
    def patch(self):
        request = tornado.escape.json_decode(self.request.body)
        response = {
            "FileID": None,
            "Modifications": []
        }
        if "UserName" in request and "UserPassword" in request and "FileID" in request and "Modifications" in request:
            UserID = check_user(request["UserName"], request["UserPassword"])
            if UserID:
                FileID = check_private_file(request["FileID"], UserID)
                if FileID == request["FileID"]:     
                    base_query = "UPDATE Files SET {0} = ? WHERE FileID = " + str(FileID)
                    for modification in request["Modifications"]:
                        try:
                            if modification in ["FileDescription", "FileNSFW", "FilePrivate"]:
                                storedb_cursor.execute(base_query.format(modification), (request["Modifications"][modification],))
                            elif modification == "DeleteFile":
                                delete_file(FileID)
                            storedb_connection.commit()
                            response["Modifications"].append(modification)
                        except:
                            logging.exception("Could not apply requested modification '{0}'!".format(modification))
                    response["FileID"] = request["FileID"]
                    self.write(response)
                else:
                    self.set_status(404)
                    response["FileID"] = request["FileID"]
                    self.write(response)
            else:
                self.set_status(401)
                self.write(response)
        else:
            self.set_status(400)
            self.write(response)
                        

class FileInfoHandler(tornado.web.RequestHandler):
    def prepare(self):
        self.response = {
            "FileID": None,
            "FileDescription": None,
            "FileNSFW": None,
            "FilePrivate": None,
            "FileMime": None,
            "FileWidth": None,
            "FileHeight": None,
            "FileCreatedDate": None
        }

    def set_response(self, filemeta):
        self.response["FileID"] = filemeta[0]
        self.response["FileDescription"] = filemeta[2]
        self.response["FileNSFW"] = bool(filemeta[3])
        self.response["FilePrivate"] = bool(filemeta[4])
        self.response["FileMime"] = filemeta[5]
        self.response["FileWidth"] = filemeta[6]
        self.response["FileHeight"] = filemeta[7]
        self.response["FileCreatedDate"] = filemeta[8]

    def get(self, FileID):
        def perform_request():
            filemeta = storedb_cursor.execute("SELECT * FROM Files WHERE FileID = ?", (FileID,)).fetchone()
            if filemeta:
                self.set_response(filemeta)
                self.write(self.response)
            else:
                self.set_status(404)
                self.write(self.response)

        if FileID != "":
            FilePrivate = storedb_cursor.execute("SELECT FilePrivate FROM Files WHERE FileID = ?", (FileID,)).fetchone()
            if FilePrivate:
                if FilePrivate[0]:
                    if self.request.headers.get("Authorization"):
                        auth_header = self.request.headers.get("Authorization").split(" ")
                        if auth_header[0] == "Basic":
                            auth_deciphered = base64.b64decode(auth_header[1].encode('utf-8')).decode('utf-8').split(":")
                            if len(auth_deciphered) == 2:
                                UserID = check_user(auth_deciphered[0], auth_deciphered[1])
                                if UserID:
                                    if FileID == check_private_file(FileID, UserID):
                                        perform_request()   
                                else:
                                    self.set_status(401)
                                    self.write(self.response)
                            else:
                                self.set_status(400)
                                self.write(self.response)
                        else:
                            self.set_status(400)
                            self.write(self.response)
                    else:
                        self.set_status(401)
                        self.write(self.response)
                else:
                    perform_request()
            else:
                self.set_status(404)
                self.write(self.response)
        else:
            self.set_status(400)
            self.write(self.response)

class EmbedImgGeneratorHandler(tornado.web.RequestHandler):
    def get(self, FileID):
        def perform_request():
            filemeta = storedb_cursor.execute("SELECT FileName, FileMime FROM Files WHERE FileID = ?", (FileID,)).fetchone()
            if filemeta:
                filepath = os.path.join(FILES_PATH, str(FileID), str(filemeta[0]))
                if os.path.isfile(filepath):
                    self.set_header('Content-Type', filemeta[1])
                    with open(filepath, 'rb') as file:
                        self.write(file.read())
                else:
                    self.send_error(404)
            else:
                self.send_error(404)

        if FileID != "":
            FilePrivate = storedb_cursor.execute("SELECT FilePrivate FROM Files WHERE FileID = ?", (FileID,)).fetchone()
            if FilePrivate:
                if FilePrivate[0]:
                    if self.request.headers.get("Authorization"):
                        auth_header = self.request.headers.get("Authorization").split(" ")
                        if auth_header[0] == "Basic":
                            auth_deciphered = base64.b64decode(auth_header[1].encode('utf-8')).decode('utf-8').split(":")
                            if len(auth_deciphered) == 2:
                                UserID = check_user(auth_deciphered[0], auth_deciphered[1])
                                if UserID:
                                    if FileID == check_private_file(FileID, UserID):
                                        perform_request()
                                    else:
                                        self.send_error(401)
                                else:
                                    self.send_error(401)
                            else:
                                self.send_error(400)
                        else:
                            self.send_error(400)
                    else:
                        self.send_error(401)
                else:
                    perform_request()
            else:
                self.send_error(404)
        else:
            self.send_error(400)

class EmbedFileHandler(tornado.web.RequestHandler):
    def get(self, FileID):
        if FileID != "":
            filemeta = storedb_cursor.execute("SELECT FileName, FileDescription, FileMime, FileWidth, FileHeight, FilePrivate FROM Files WHERE FileID = ?", (FileID,)).fetchone()
            if filemeta:
                if not bool(filemeta[5]):
                    self.render(
                        "embed-template.html",
                        title=filemeta[0] + " - on Iamages",
                        FileDescription=filemeta[1],
                        FileID=FileID,
                        FileMime=filemeta[2],
                        FileWidth=filemeta[3],
                        FileHeight=filemeta[4]
                    )
                else:
                    self.render(
                        "embed-template.html",
                        title="Private File from Iamages",
                        FileDescription="You're not allowed to view this file.\nContact the owner.",
                        FileID=0,
                        FileMime="",
                        FileWidth=0,
                        FileHeight=0
                    )
            else:
                self.send_error(404)
        else:
            self.send_error(400)

class UserInfoHandler(tornado.web.RequestHandler):
    def get(self, UserName):
        response = {
            "UserName": None,
            "UserInfo": {}
        }
        if UserName != "":
            response["UserName"] = UserName
            usermeta = storedb_cursor.execute('SELECT UserBiography, UserCreatedDate FROM Users WHERE UserName = ?', (UserName,)).fetchone()
            if usermeta:
                response["UserInfo"]["UserBiography"] = usermeta[0]
                response["UserInfo"]["UserCreatedDate"] = usermeta[1]
                self.write(response)
            else:
                self.send_error(404)
        else:
            self.send_error(400)


class UserFilesHandler(tornado.web.RequestHandler):
    def post(self):
        request = tornado.escape.json_decode(self.request.body)
        response = {
            "UserName": None,
            "FileIDs": None 
        }
        if "UserName" in request and "UserPassword" in request:
            UserID = check_user(request["UserName"], request["UserPassword"])
            if UserID:
                files = storedb_cursor.execute("SELECT FileID FROM Files_Users WHERE UserID = ?", (UserID,)).fetchall()
                response["UserName"] = request["UserName"]
                response["FileIDs"] = []
                for file in files:
                    response["FileIDs"].append(file[0])
                self.write(response)
            else:
                self.set_status(401)
                self.write(response)
        else:
            self.set_status(400)
            self.write(response)

class UserModifyHandler(tornado.web.RequestHandler):
    def patch(self):
        request = tornado.escape.json_decode(self.request.body)
        response = {
            "UserName": None,
            "Modifications": []
        }
        if "UserName" in request and "UserPassword" in request and "Modifications" in request:
            UserID = check_user(request["UserName"], request["UserPassword"])
            if UserID:
                basic_query = "UPDATE Users SET {0} = ? WHERE UserID = " + str(UserID)
                for modification in request["Modifications"]:
                    try:
                        if modification in ["UserBiography", "UserName"]:
                            storedb_cursor.execute(basic_query.format(modification), (request["Modifications"][modification],))
                        elif modification == "UserPassword":
                            storedb_cursor.execute(basic_query.format(modification), (bcrypt.hashpw(bytes(request["Modifications"][modification], 'utf-8'), bcrypt.gensalt()),))
                        elif modification == "DeleteUser":
                            storedb_cursor.execute("DELETE FROM Users WHERE UserID = ?", (UserID,))
                            FileIDs = storedb_cursor.execute("SELECT FileID From Files_Users WHERE UserID = ?", (UserID,)).fetchall()
                            for FileID in FileIDs:
                                delete_file(FileID[0])
                        storedb_connection.commit()
                        response["Modifications"].append(modification)
                    except:
                        logging.exception("Could not apply requested modification '{0}'!".format(modification))
                response["UserName"] = request["UserName"]
                self.write(response)
            else:
                self.set_status(401)
                self.write(response)
        else:
            self.set_status(400)
            self.write(response)


class NewUserHandler(tornado.web.RequestHandler):
    def put(self):
        request = tornado.escape.json_decode(self.request.body)
        response = {
            "UserName": None
        }
        if "UserName" in request and "UserPassword" in request:
            if check_user(request["UserName"], request["UserPassword"]):
                self.set_status(403)
                self.write(response)
            else:
                storedb_cursor.execute("INSERT INTO Users (UserName, UserPassword, UserCreatedDate) VALUES (?, ?, datetime('now'))", (request["UserName"], bcrypt.hashpw(bytes(request["UserPassword"], 'utf-8'), bcrypt.gensalt())))
                storedb_connection.commit()
                response["UserName"] = request["UserName"]
                self.write(response)
        else:
            self.set_status(400)
            self.write(response)

class CheckUserHandler(tornado.web.RequestHandler):
    def post(self):
        request = tornado.escape.json_decode(self.request.body)
        response = {
            "UserName": None
        }
        if "UserName" in request and "UserPassword" in request:
            if check_user(request["UserName"], request["UserPassword"]):
                response["UserName"] = request["UserName"]
                self.write(response)
            else:
                self.set_status(401)
                self.write(response)
        else:
            self.set_status(400)
            self.write(response)

app_endpoints = [
    (r'/iamages/api/?', RootInfoHandler),
    (r'/iamages/api/latest/?', LatestFilesHandler),
    (r'/iamages/api/random/?', RandomFileHandler),
    (r'/iamages/api/upload/?', FileUploadHandler),
    (r'/iamages/api/modify/?', FileModifyHandler),
    (r'/iamages/api/info/(.*\d)/?', FileInfoHandler),
    (r'/iamages/api/embed/(.*\d)/?', EmbedFileHandler),
    (r'/iamages/api/img/(.*\d)/?', EmbedImgGeneratorHandler),
    (r'/iamages/api/user/info/(.*)/?', UserInfoHandler),
    (r'/iamages/api/user/files/?', UserFilesHandler),
    (r'/iamages/api/user/modify/?', UserModifyHandler),
    (r'/iamages/api/user/new/?', NewUserHandler),
    (r'/iamages/api/user/check/?', CheckUserHandler),
    (r'/iamages/api/private/tos/?', TOSHandler),
    (r'/iamages/api/private/privacy/?', PrivacyPolicyHandler)
]

app_settings = {
    "static_path": os.path.join(IAMAGES_PATH, "assets"),
    "static_url_prefix": "/iamages/api/private/assets/",
    "debug": False,
    "gzip": True,
}

application = tornado.web.Application(app_endpoints, **app_settings)

if "keys" in server_config:
    if server_config["keys"]["directory"] != "":
        ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_ctx.load_cert_chain(os.path.join(server_config["keys"]["directory"], server_config["keys"]["files"]["chain"]),
                                os.path.join(server_config["keys"]["directory"], server_config["keys"]["files"]["private"]))
        application.listen(server_config['port'])
        application.listen(server_config["port_secure"], ssl_options=ssl_ctx)
        logging.info("Listening for requests on port {0} and {1}!".format(server_config["port_secure"], server_config["port"]))
    else:
        application.listen(server_config['port'])
        logging.info("Listening for requests on port {0}!".format(server_config["port"]))
else:
    application.listen(server_config['port'])
    logging.info("Listening for requests on port {0}!".format(server_config["port"]))
tornado.ioloop.IOLoop.current().start()
