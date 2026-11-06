#include "audiobackend.h"
#include <QDir>
#include <QElapsedTimer>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLocalSocket>
#include <QtMath>
#include <unistd.h>

AudioBackend::AudioBackend(Request request, QObject *parent)
    : QObject(parent), m_request(request ? request : requestLocal) {}

QByteArray AudioBackend::requestLocal(const QByteArray &command)
{
    const QString runtime = qEnvironmentVariable("XDG_RUNTIME_DIR", QString("/run/user/%1").arg(getuid()));
    QLocalSocket socket;
    socket.connectToServer(QDir(runtime).filePath("omarchy-uow-audio/worker.sock"));
    if (!socket.waitForConnected(300)) return {};
    socket.write(command);
    if (!socket.waitForBytesWritten(300) && socket.bytesToWrite()) return {};
    QElapsedTimer timer;
    timer.start();
    QByteArray result;
    while (!result.endsWith('\n') && result.size() <= 4096) {
        const int remaining = 500 - int(timer.elapsed());
        if (remaining <= 0 || (socket.bytesAvailable() == 0 && !socket.waitForReadyRead(remaining))) return {};
        result += socket.readAll();
    }
    return result.size() <= 4096 && result.endsWith('\n') ? result : QByteArray();
}

bool AudioBackend::canApply() const
{
    return m_state == "streaming" && m_receiverAge >= 0 && m_receiverAge <= 3
           && m_currentLow > 0 && m_currentHigh > m_currentLow
           && qIsFinite(m_editLow) && qIsFinite(m_editHigh)
           && 0 < m_editLow && m_editLow < m_editHigh && m_editHigh < 24000
           && m_changeState != "pending";
}

void AudioBackend::setEditLow(double value)
{
    m_editLow = value;
    m_dirty = true;
    emit changed();
}

void AudioBackend::setEditHigh(double value)
{
    m_editHigh = value;
    m_dirty = true;
    emit changed();
}

bool AudioBackend::updateFromStatus(const QByteArray &response)
{
    if (response.isEmpty() || response.size() > 4096) return false;
    QJsonParseError error;
    const QJsonDocument document = QJsonDocument::fromJson(response, &error);
    if (error.error != QJsonParseError::NoError || !document.isObject()) return false;
    const QJsonObject value = document.object();
    const QJsonValue state = value.value("state");
    const QJsonValue enabled = value.value("enabled");
    const QJsonValue source = value.value("source");
    if (!state.isString() || state.toString().size() > 40 || !enabled.isBool()
        || (!source.isNull() && (!source.isString() || source.toString().size() > 160))) return false;
    m_state = state.toString();
    m_enabled = enabled.toBool();
    m_source = source.isString() ? source.toString() : QString();
    const QJsonValue age = value.value("receiver_age_s");
    m_receiverAge = age.isDouble() && qIsFinite(age.toDouble()) && age.toDouble() >= 0 ? age.toDouble() : -1;
    const QJsonValue low = value.value("crossover_low_hz");
    const QJsonValue high = value.value("crossover_high_hz");
    m_currentLow = low.isDouble() && qIsFinite(low.toDouble()) && low.toDouble() > 0 ? low.toDouble() : -1;
    m_currentHigh = high.isDouble() && qIsFinite(high.toDouble()) && high.toDouble() > m_currentLow ? high.toDouble() : -1;
    const QJsonValue change = value.value("crossover_change");
    if (change.isObject() && change.toObject().value("state").isString()) {
        const QString next = change.toObject().value("state").toString();
        if (QStringList{"idle", "pending", "receiver-reported", "unconfirmed", "interrupted", "denied"}.contains(next))
            m_changeState = next;
    }
    if (!m_dirty || m_changeState == "receiver-reported") {
        m_editLow = m_currentLow;
        m_editHigh = m_currentHigh;
        m_dirty = false;
    }
    emit changed();
    return true;
}

bool AudioBackend::refresh()
{
    if (updateFromStatus(m_request("status\n"))) return true;
    m_state = "unavailable";
    m_enabled = false;
    m_receiverAge = -1;
    m_currentLow = -1;
    m_currentHigh = -1;
    if (m_changeState == "pending") m_changeState = "unconfirmed";
    emit changed();
    return false;
}

bool AudioBackend::setStreaming(bool enabled)
{
    const bool ok = updateFromStatus(m_request(enabled ? "on\n" : "off\n"));
    if (!ok) refresh();
    return ok;
}

bool AudioBackend::apply()
{
    if (!canApply()) return false;
    const QByteArray command = "crossover " + QByteArray::number(m_editLow, 'g', 12)
                               + " " + QByteArray::number(m_editHigh, 'g', 12) + "\n";
    const QByteArray response = m_request(command);
    if (response.isEmpty() || response.size() > 4096) return false;
    const QJsonDocument document = QJsonDocument::fromJson(response);
    if (!document.isObject()) return false;
    const QString state = document.object().value("state").toString();
    if (!QStringList{"pending", "denied", "busy", "receiver-unavailable", "reconciliation-pending", "interrupted"}.contains(state)) return false;
    m_changeState = state;
    emit changed();
    return state == "pending";
}

void AudioBackend::revertEdits()
{
    m_editLow = m_currentLow;
    m_editHigh = m_currentHigh;
    m_dirty = false;
    emit changed();
}
