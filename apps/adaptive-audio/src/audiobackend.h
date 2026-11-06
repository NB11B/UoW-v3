#pragma once

#include <QObject>
#include <QByteArray>
#include <functional>

class AudioBackend : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString state READ state NOTIFY changed)
    Q_PROPERTY(QString source READ source NOTIFY changed)
    Q_PROPERTY(double receiverAge READ receiverAge NOTIFY changed)
    Q_PROPERTY(double packetRate READ packetRate NOTIFY changed)
    Q_PROPERTY(double currentLow READ currentLow NOTIFY changed)
    Q_PROPERTY(double currentHigh READ currentHigh NOTIFY changed)
    Q_PROPERTY(double editLow READ editLow WRITE setEditLow NOTIFY changed)
    Q_PROPERTY(double editHigh READ editHigh WRITE setEditHigh NOTIFY changed)
    Q_PROPERTY(bool enabled READ enabled NOTIFY changed)
    Q_PROPERTY(bool canApply READ canApply NOTIFY changed)
    Q_PROPERTY(QString changeState READ changeState NOTIFY changed)
public:
    using Request = std::function<QByteArray(const QByteArray &)>;
    explicit AudioBackend(Request request = {}, QObject *parent = nullptr);
    QString state() const { return m_state; }
    QString source() const { return m_source; }
    double receiverAge() const { return m_receiverAge; }
    double packetRate() const { return m_packetRate; }
    double currentLow() const { return m_currentLow; }
    double currentHigh() const { return m_currentHigh; }
    double editLow() const { return m_editLow; }
    double editHigh() const { return m_editHigh; }
    bool enabled() const { return m_enabled; }
    bool canApply() const;
    QString changeState() const { return m_changeState; }
    void setEditLow(double value);
    void setEditHigh(double value);
    Q_INVOKABLE bool refresh();
    Q_INVOKABLE bool setStreaming(bool enabled);
    Q_INVOKABLE bool apply();
    Q_INVOKABLE void revertEdits();
signals:
    void changed();
private:
    static QByteArray requestLocal(const QByteArray &command);
    bool updateFromStatus(const QByteArray &response);
    Request m_request;
    QString m_state = "unavailable";
    QString m_source;
    QString m_changeState = "idle";
    double m_receiverAge = -1;
    double m_packetRate = -1;
    double m_currentLow = -1;
    double m_currentHigh = -1;
    double m_editLow = -1;
    double m_editHigh = -1;
    bool m_enabled = false;
    bool m_dirty = false;
};
