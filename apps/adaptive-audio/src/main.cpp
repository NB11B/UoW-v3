#include <QDir>
#include <QGuiApplication>
#include <QLocalServer>
#include <QLocalSocket>
#include <QLockFile>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickWindow>
#include <QTimer>
#include <QWindow>
#include "audiobackend.h"
#include "theme.h"
#include <unistd.h>

int main(int argc, char **argv)
{
    QGuiApplication app(argc, argv);
    app.setDesktopFileName("adaptive-audio");
    const QStringList args = app.arguments();
    const bool smoke = args.size() == 2 && args.at(1) == "--ui-smoke";
    const bool shot = args.size() == 3 && args.at(1) == "--ui-shot";
    if (!smoke && !shot && !(args.size() == 2 && args.at(1) == "open")) return 1;

    const QString runtime = qEnvironmentVariable("XDG_RUNTIME_DIR", QString("/run/user/%1").arg(getuid()));
    const QString uiSocket = QDir(runtime).filePath("adaptive-audio-ui.sock");
    QLockFile lock(uiSocket + ".lock");
    QLocalServer server;
    if (!smoke && !shot) {
        lock.setStaleLockTime(0);
        if (!lock.tryLock(0)) {
            QLocalSocket existing;
            existing.connectToServer(uiSocket);
            if (!existing.waitForConnected(500)) return 1;
            existing.write("show\n");
            if (!existing.waitForBytesWritten(500) && existing.bytesToWrite()) return 1;
            return existing.waitForReadyRead(500) && existing.readAll() == "ok\n" ? 0 : 1;
        }
        server.setSocketOptions(QLocalServer::UserAccessOption);
        QLocalServer::removeServer(uiSocket);
        if (!server.listen(uiSocket)) return 1;
    }

    AudioBackend backend;
    Theme theme;
    QQmlApplicationEngine engine;
    engine.rootContext()->setContextProperty("backend", &backend);
    engine.rootContext()->setContextProperty("theme", &theme);
    engine.load(QUrl("qrc:/Main.qml"));
    if (engine.rootObjects().isEmpty()) return 1;
    QWindow *window = qobject_cast<QWindow *>(engine.rootObjects().first());
    if (!window) return 1;
    if (!smoke && !shot) {
        QObject::connect(&server, &QLocalServer::newConnection, &app, [&server, window] {
            while (auto *client = server.nextPendingConnection()) {
                QObject::connect(client, &QLocalSocket::readyRead, client, [client, window] {
                    if (client->readAll() == "show\n") {
                        window->show(); window->raise(); window->requestActivate();
                        client->write("ok\n");
                    } else client->write("error\n");
                    client->flush(); client->disconnectFromServer();
                });
                QObject::connect(client, &QLocalSocket::disconnected, client, &QObject::deleteLater);
            }
        });
    }
    backend.refresh();
    QTimer poll;
    poll.setInterval(1000);
    QObject::connect(&poll, &QTimer::timeout, &backend, &AudioBackend::refresh);
    poll.start();
    if (smoke) QTimer::singleShot(700, &app, &QGuiApplication::quit);
    if (shot) QTimer::singleShot(700, &app, [window, &app, args] {
        auto *quick = qobject_cast<QQuickWindow *>(window);
        if (quick) quick->grabWindow().save(args.at(2));
        app.quit();
    });
    const int result = app.exec();
    if (!smoke && !shot) QLocalServer::removeServer(uiSocket);
    return result;
}
