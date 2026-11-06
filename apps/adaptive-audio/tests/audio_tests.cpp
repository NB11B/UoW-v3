#include <QtTest>
#include <QDir>
#include <QLocalServer>
#include <QLocalSocket>
#include <QTemporaryDir>
#include <QThread>
#include <future>
#include "audiobackend.h"

class AudioTests : public QObject {
    Q_OBJECT
private slots:
    void readsReceiverAndRequiresExplicitApply();
    void staleReceiverPreventsApply();
    void streamToggleAndDestructionDoNotSendExtraCommands();
    void workerLossClearsVisibleState();
    void readsFragmentedSocketResponse();
    void preservesNewEditsAfterReceiverReport();
    void clearsSuccessWhenReceiverLost();
};

static QByteArray status(double age = 0.2)
{
    return QByteArray("{\"state\":\"streaming\",\"source\":\"speaker.monitor\",\"receiver_age_s\":")
        + QByteArray::number(age) +
        QByteArray(",\"crossover_low_hz\":100,\"crossover_high_hz\":2500,\"enabled\":true,\"crossover_change\":{\"state\":\"idle\"}}\n");
}

void AudioTests::readsReceiverAndRequiresExplicitApply()
{
    QList<QByteArray> commands;
    AudioBackend backend([&](const QByteArray &command) {
        commands.append(command);
        return command.startsWith("crossover ") ? QByteArray("{\"state\":\"pending\"}\n") : status();
    });
    backend.refresh();
    QCOMPARE(backend.currentLow(), 100.0);
    QCOMPARE(backend.currentHigh(), 2500.0);
    QVERIFY(backend.canApply());
    backend.setEditLow(120);
    backend.setEditHigh(2200);
    QCOMPARE(commands.size(), 1);
    QVERIFY(backend.apply());
    QCOMPARE(commands.size(), 2);
    QCOMPARE(commands.last(), QByteArray("crossover 120 2200\n"));
    QCOMPARE(backend.changeState(), QString("pending"));
}

void AudioTests::staleReceiverPreventsApply()
{
    QList<QByteArray> commands;
    AudioBackend backend([&](const QByteArray &command) { commands.append(command); return status(4.0); });
    backend.refresh();
    QVERIFY(!backend.canApply());
    backend.setEditLow(120);
    backend.setEditHigh(2200);
    QVERIFY(!backend.apply());
    QCOMPARE(commands.size(), 1);
}

void AudioTests::streamToggleAndDestructionDoNotSendExtraCommands()
{
    QList<QByteArray> commands;
    {
        AudioBackend backend([&](const QByteArray &command) { commands.append(command); return status(); });
        backend.refresh();
        backend.setStreaming(false);
        QCOMPARE(commands.last(), QByteArray("off\n"));
    }
    QCOMPARE(commands.size(), 2);
}

void AudioTests::workerLossClearsVisibleState()
{
    bool available = true;
    AudioBackend backend([&](const QByteArray &) { return available ? status() : QByteArray(); });
    backend.refresh();
    QVERIFY(backend.enabled());
    available = false;
    QVERIFY(!backend.refresh());
    QCOMPARE(backend.state(), QString("unavailable"));
    QVERIFY(!backend.enabled());
    QVERIFY(!backend.canApply());
}

void AudioTests::preservesNewEditsAfterReceiverReport()
{
    QByteArray live = status();
    AudioBackend backend([&](const QByteArray &command) {
        return command.startsWith("crossover ") ? QByteArray("{\"state\":\"pending\"}\n") : live;
    });
    backend.refresh();
    backend.setEditLow(120);
    backend.setEditHigh(2200);
    QVERIFY(backend.apply());
    live = "{\"state\":\"streaming\",\"source\":\"speaker.monitor\",\"receiver_age_s\":0.2,\"crossover_low_hz\":120,\"crossover_high_hz\":2200,\"enabled\":true,\"crossover_change\":{\"state\":\"receiver-reported\"}}\n";
    backend.refresh();
    backend.setEditLow(130);
    backend.refresh();
    QCOMPARE(backend.editLow(), 130.0);
    QCOMPARE(backend.changeState(), QString("receiver-reported"));
}

void AudioTests::clearsSuccessWhenReceiverLost()
{
    QByteArray live = "{\"state\":\"streaming\",\"source\":\"speaker.monitor\",\"receiver_age_s\":0.2,\"crossover_low_hz\":120,\"crossover_high_hz\":2200,\"enabled\":true,\"crossover_change\":{\"state\":\"receiver-reported\"}}\n";
    AudioBackend backend([&](const QByteArray &) { return live; });
    backend.refresh();
    QCOMPARE(backend.changeState(), QString("receiver-reported"));
    live = "{\"state\":\"receiver-wait\",\"source\":null,\"receiver_age_s\":null,\"crossover_low_hz\":null,\"crossover_high_hz\":null,\"enabled\":true,\"crossover_change\":{\"state\":\"receiver-reported\"}}\n";
    backend.refresh();
    QCOMPARE(backend.changeState(), QString("unconfirmed"));
}

void AudioTests::readsFragmentedSocketResponse()
{
    QTemporaryDir dir;
    QVERIFY(dir.isValid());
    QDir().mkpath(dir.path() + "/omarchy-uow-audio");
    const QByteArray previous = qgetenv("XDG_RUNTIME_DIR");
    qputenv("XDG_RUNTIME_DIR", dir.path().toUtf8());
    std::promise<bool> ready;
    auto listening = ready.get_future();
    QThread *serverThread = QThread::create([&] {
        QLocalServer server;
        const bool ok = server.listen(dir.path() + "/omarchy-uow-audio/worker.sock");
        ready.set_value(ok);
        if (!ok || !server.waitForNewConnection(2000)) return;
        std::unique_ptr<QLocalSocket> client(server.nextPendingConnection());
        if (!client || !client->waitForReadyRead(1000)) return;
        client->readAll();
        const QByteArray response = status();
        const int split = response.size() / 2;
        client->write(response.left(split));
        client->waitForBytesWritten(1000);
        QThread::msleep(40);
        client->write(response.mid(split));
        client->waitForBytesWritten(1000);
        QThread::msleep(40);
    });
    serverThread->start();
    const bool opened = listening.get();
    AudioBackend backend;
    const bool refreshed = opened && backend.refresh();
    serverThread->wait();
    delete serverThread;
    if (previous.isEmpty()) qunsetenv("XDG_RUNTIME_DIR");
    else qputenv("XDG_RUNTIME_DIR", previous);
    QVERIFY(opened);
    QVERIFY(refreshed);
    QCOMPARE(backend.currentHigh(), 2500.0);
}

QTEST_MAIN(AudioTests)
#include "audio_tests.moc"
