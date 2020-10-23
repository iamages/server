import base64
import sqlite3
import json
import os
import logging
import bcrypt
import ssl
import magic
import tornado.web
import tornado.escape
import tornado.ioloop

logging.basicConfig(format='SERVER | %(asctime)s | %(levelname)s | %(message)s', datefmt='%d/%m/%y %H:%M:%S', level=logging.INFO)

IAMAGES_PATH = os.path.dirname(__file__)

logging.info("Starting imgcloud server...")
logging.info("Loading server configuration file...")
try:
    server_config = json.load(open(os.path.join(IAMAGES_PATH, 'servercfg.json'), "r"))
    logging.info("Loaded server configuration file!")
except Exception:
    logging.exception("Server config load failed! Halting...", exc_info=True)
    exit()

if not os.path.isdir(server_config["storage_directory"]):
    os.makedirs(server_config["storage_directory"])

FILESDB_PATH = os.path.join(server_config["storage_directory"], "store.db")

logging.info("Connecting to storage database...")
storedb_connection = sqlite3.connect(FILESDB_PATH)
storedb_cursor = storedb_connection.cursor()

if storedb_cursor.execute("SELECT name FROM sqlite_master").fetchall() == []:
    logging.info("Storage database is new, creating tables...")
    with open(os.path.join(IAMAGES_PATH, "store.sql"), "r") as query:
        storedb_cursor.executescript(query.read())

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

class RootInfoHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("api-doc.html")

class LatestFilesHandler(tornado.web.RequestHandler):
    def get(self):
        response = {
            "FileIDs": []
        }
        try: 
            files = storedb_cursor.execute("SELECT FileID FROM Files ORDER BY FileID DESC LIMIT 10").fetchall()
            for file in files:
                response["FileIDs"].append(file[0])
        except:
            logging.exception("Failed to get latest list!")
        self.write(response)

class FileUploadHandler(tornado.web.RequestHandler):
    def put(self):
        request = tornado.escape.json_decode(self.request.body)
        response = {
            "FileName": None
        }
        if not "FileName" in request or not "FileData" in request or not "FileNSFW" in request or not "FileDescription" in request:
            self.set_status(400)
            self.write(response)
        else:
            storedb_cursor.execute("INSERT INTO Files (FileName, FileDescription, FileNSFW, FileCreatedDate) VALUES (?, ?, ?, datetime('now'))", (request["FileName"], request["FileDescription"], request["FileNSFW"]))
            FileID = storedb_cursor.execute("SELECT FileID FROM Files ORDER BY FileID DESC").fetchone()[0]
            folderpath = os.path.join(FILES_PATH, str(FileID))
            if not os.path.isdir(folderpath):
                os.makedirs(folderpath)
            filepath = os.path.join(folderpath, request["FileName"])
            with open(filepath, "wb") as file:
                file.write(base64.b64decode(request["FileData"]))
            storedb_cursor.execute("UPDATE Files SET FileMime = ? WHERE FileID = ?", (magic.from_file(filepath, mime=True), FileID))
            if "UserName" in request and "UserPassword" in request:
                UserID = check_user(request["UserName"], request["UserPassword"])
                if UserID:
                    storedb_cursor.execute("INSERT INTO Files_Users (FileID, UserID) VALUES (?, ?)", (FileID, UserID))
            storedb_connection.commit()
            response["FileName"] = request["FileName"]
            self.write(response)

class FileModifyHandler(tornado.web.RequestHandler):
    def patch(self):
        request = tornado.escape.json_decode(self.request.body)
        response = {
            "FileID": None,
            "Modifications": []
        }
        if not "UserName" in request or not "UserPassword" in request or not "FileID" in request or not "Modifications" in request:
            self.set_status(400)
            self.write(response)
        else:
            UserID = check_user(request["UserName"], request["UserPassword"])
            if UserID:
                FileID = storedb_cursor.execute("SELECT FileID FROM Files_Users WHERE FileID = ? AND UserID = ?", (request["FileID"], UserID)).fetchone()[0]
                if FileID == request["FileID"]:
                    base_query = "UPDATE Files SET {0} = ? WHERE FileID = " + str(FileID)
                    for modification in request["Modifications"]:
                        try:
                            if modification == "FileDescription" or modification == "FileNSFW":
                                storedb_cursor.execute(base_query.format(modification), (request["Modifications"][modification],))
                            elif modification == "DeleteFile":
                                storedb_cursor.execute("DELETE FROM Files WHERE FileID = ?", (request["FileID"]))
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
                        

class GetFileHandler(tornado.web.RequestHandler):
    def post(self):
        request = tornado.escape.json_decode(self.request.body)
        response = {
            "FileID": None,
            "FileData": None
        }
        if not "FileID" in request:
            self.set_status(400)
            self.write(response)
        else:
            filemeta = storedb_cursor.execute("SELECT * FROM Files WHERE FileID = ?", (request["FileID"],)).fetchone()
            if filemeta:
                filepath = os.path.join(FILES_PATH, str(request["FileID"]), str(filemeta[1]))
                if not os.path.isfile(filepath):
                    self.set_status(404)
                    response["FileID"] = request["FileID"]
                    self.write(response)
                else:
                    with open(filepath, 'rb') as file:
                        self.write({
                            "FileID": request["FileID"],
                            "FileName": filemeta[1],
                            "FileDescription": filemeta[2],
                            "FileCreatedDate": filemeta[3],
                            "FileData": base64.b64encode(file.read()).decode('utf-8')
                        })
            else:
                self.set_status(404)
                response["FileID"] = request["FileID"]
                self.write(response)

class EmbedFileHandler(tornado.web.RequestHandler):
    def get(self):
        try:
            FileID = self.request.path.split("/")[-1]
            if FileID != "":
                filemeta = storedb_cursor.execute("SELECT FileName, FileDescription, FileMime FROM Files WHERE FileID = ?", (FileID,)).fetchone()
                if filemeta:
                    filepath = os.path.join(FILES_PATH, str(FileID), str(filemeta[0]))
                    if os.path.isfile(filepath):
                        with open(filepath, 'rb') as file:
                            self.render(
                                "embed-template.html",
                                title=filemeta[0] + " - on Iamages",
                                description=filemeta[1],
                                image="data:{0};base64,{1}".format(filemeta[2], base64.b64encode(file.read()).decode('utf-8'))
                            )
                    else:
                        self.send_error(404)
                else:
                    self.send_error(404)
            else:
                self.send_error(400)
        except:
            logging.exception('Something wrong!')
            self.render(
                "embed-template.html",
                title="Error from Iamages",
                description="We couldn't find the file you wanted :(",
                image=""
            )

class UserInfoHandler(tornado.web.RequestHandler):
    def post(self):
        request = tornado.escape.json_decode(self.request.body)
        response = {
            "UserName": None,
            "UserDetails": {}
        }
        if not "UserName" in request or not "UserDetails" in request:
            self.set_status(400)
            self.write(response)
        else:
            basic_query = "SELECT {0} FROM Users WHERE UserName = '" + str(request["UserName"]) + "'"
            for UserDetail in request["UserDetails"]:
                if UserDetail == "UserBiography" or UserDetail == "UserCreatedDate":
                    try:
                        response["UserDetails"][UserDetail] = storedb_cursor.execute(basic_query.format(UserDetail)).fetchone()[0]
                    except:
                        logging.exception("Failed to get UserDetail '{0}'!".format(UserDetail))
                else:
                    logging.warning("Unsupported field '{0}'. Not processing!".format(UserDetail))
            response["UserName"] = request["UserName"]
            self.write(response)


class UserFilesHandler(tornado.web.RequestHandler):
    def post(self):
        request = tornado.escape.json_decode(self.request.body)
        response = {
            "UserName": None,
            "UserFiles": None 
        }
        if not "UserName" in request or not "UserPassword" in request:
            self.set_status(400)
            self.write(response)
        else:
            userid = check_user(request["UserName"], request["UserPassword"])
            if userid:
                files = storedb_cursor.execute("SELECT FileID FROM Files_Users INNER JOIN Users ON Files_Users.UserID = Users.UserID WHERE Users.UserID = ?", (userid,)).fetchall()
                response["UserName"] = request["UserName"]
                response["UserFiles"] = []
                for file in files:
                    response["UserFiles"].append(file[0])
                self.write(response)
            else:
                self.set_status(401)
                self.write(response)

class UserModifyHandler(tornado.web.RequestHandler):
    def patch(self):
        request = tornado.escape.json_decode(self.request.body)
        response = {
            "UserName": None,
            "Modifications": []
        }
        if not "UserName" in request or not "UserPassword" in request or not "Modifications" in request:
            self.set_status(400)
            self.write(response)
        else:
            UserID = check_user(request["UserName"], request["UserPassword"])
            if UserID:
                basic_query = "UPDATE Users SET {0} = ? WHERE UserID = " + str(UserID)
                for modification in request["Modifications"]:
                    try:
                        if modification == "UserBiography" or modification == "UserName":
                            storedb_cursor.execute(basic_query.format(modification), (request["Modifications"][modification],))
                        elif modification == "UserPassword":
                            storedb_cursor.execute(basic_query.format(modification), (bcrypt.hashpw(bytes(request["Modifications"][modification], 'utf-8'), bcrypt.gensalt()),))
                        storedb_connection.commit()
                        response["Modifications"].append(modification)
                    except:
                        logging.exception("Could not apply requested modification '{0}'!".format(modification))
                response["UserName"] = request["UserName"]
                self.write(response)
            else:
                self.set_status(401)
                self.write(response)


class NewUserHandler(tornado.web.RequestHandler):
    def put(self):
        request = tornado.escape.json_decode(self.request.body)
        response = {
            "UserName": None
        }
        if not "UserName" in request or not "UserPassword" in request:
            self.set_status(400)
            self.write(response)
        else:
            if check_user(request["UserName"], request["UserPassword"]):
                self.set_status(403)
                self.write(response)
            else:
                storedb_cursor.execute("INSERT INTO Users (UserName, UserPassword, UserCreatedDate) VALUES (?, ?, datetime('now'))", (request["UserName"], bcrypt.hashpw(bytes(request["UserPassword"], 'utf-8'), bcrypt.gensalt())))
                storedb_connection.commit()
                response["UserName"] = request["UserName"]
                self.write(response)


app_endpoints = [
    (r'/iamages/api/?', RootInfoHandler),
    (r'/iamages/api/latest/?', LatestFilesHandler),
    (r'/iamages/api/upload/?', FileUploadHandler),
    (r'/iamages/api/modify/?', FileModifyHandler),
    (r'/iamages/api/get/?', GetFileHandler),
    (r'/iamages/api/embed/\d', EmbedFileHandler),
    (r'/iamages/api/user/info/?', UserInfoHandler),
    (r'/iamages/api/user/files/?', UserFilesHandler),
    (r'/iamages/api/user/modify/?', UserModifyHandler),
    (r'/iamages/api/user/new/?', NewUserHandler)
]

app_settings = {
    "debug": True,
    "gzip": True,
}

application = tornado.web.Application(app_endpoints, **app_settings)

if "keys" in server_config:
    if server_config["keys"]["directory"] != "":
        ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_ctx.load_cert_chain(os.path.join(server_config["keys"]["directory"], server_config["keys"]["files"]["certificate"]),
                                os.path.join(server_config["keys"]["directory"], server_config["keys"]["files"]["certificate_key"]))
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
