QT += core gui network testlib
CONFIG += testcase c++17
TEMPLATE = app
TARGET = adaptive-audio-tests
SOURCES += audio_tests.cpp ../src/audiobackend.cpp
HEADERS += ../src/audiobackend.h
INCLUDEPATH += ../src
