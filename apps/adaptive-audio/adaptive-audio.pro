QT += quick quickcontrols2 network
CONFIG += c++17
TEMPLATE = app
TARGET = adaptive-audio
SOURCES += src/main.cpp src/audiobackend.cpp src/theme.cpp
HEADERS += src/audiobackend.h src/theme.h
RESOURCES += src/resources.qrc
