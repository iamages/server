CREATE TABLE Files (
    FileID INTEGER PRIMARY KEY,
    FileName TEXT NOT NULL,
    FileDescription TEXT NOT NULL,
    FileNSFW INTEGER NOT NULL,
    FilePrivate INTEGER NOT NULL,
    FileMime TEXT NOT NULL,
    FileWidth INTEGER NOT NULL,
    FileHeight INTEGER NOT NULL,
    FileCreatedDate TEXT NOT NULL
);
CREATE TABLE Files_Users (
    FileID INTEGER NOT NULL,
    UserID INTEGER NOT NULL
);
CREATE TABLE Users (
    UserID INTEGER PRIMARY KEY,
    UserName TEXT NOT NULL,
    UserPassword TEXT NOT NULL,
    UserBiography TEXT,
    UserCreatedDate TEXT NOT NULL
);
CREATE TABLE Downtimes (
    Announcement TEXT NOT NULL,
    AnnouncementStart TEXT NOT NULL,
    AnnoucementEnd TEXT NOT NULL
);