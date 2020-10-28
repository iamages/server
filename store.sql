CREATE TABLE Files (
    FileID INTEGER PRIMARY KEY,
    FileName TEXT,
    FileDescription TEXT,
    FileNSFW INTEGER,
    FilePrivate INTEGER,
    FileMime TEXT,
    FileWidth INTEGER,
    FileHeight INTEGER,
    FileCreatedDate TEXT
);
CREATE TABLE Files_Users (
    FileID INTEGER,
    UserID INTEGER
);
CREATE TABLE Users (
    UserID INTEGER PRIMARY KEY,
    UserName TEXT,
    UserPassword TEXT,
    UserBiography TEXT,
    UserCreatedDate TEXT
);