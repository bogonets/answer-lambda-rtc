
class RealTimeVideoClient
{
    constructor(name, video_element_id, audio_element_id = null) {
        this.name = name;
        this.video_element_id = video_element_id;
        this.audio_element_id = audio_element_id;

        this.video_object = document.getElementById(video_element_id);
        this.audio_object = audio_element_id ? document.getElementById(audio_element_id) : null;

        this.prefix = '[rtc.realtime_video.' + name + ']';
        this.default_config = {
            sdpSemantics: 'unified-plan',
            iceServers: [
                { urls: ['stun:stun.l.google.com:19302'] }
            ]
        };

        this.pc = null;
    }

    print_debug(... args) {
        console.debug(this.prefix, ... args);
    }

    print_log(... args) {
        console.log(this.prefix, ... args);
    }

    print_error(... args) {
        console.error(this.prefix, ... args);
    }

    start() {
        this.print_debug('start()');
        this.get_config()
    }

    stop() {
        this.print_debug('stop()');
        self = this;
        setTimeout(function () {
            self.print_debug('stop() -> timeout()');
            self.pc.close();
            self.pc = null;
        }, 500);
    }

    get_config() {
        this.print_debug('get_config() fetch ...');
        self = this;
        return fetch('/config', {method: 'GET'})
            .then(function (response) {
                return response.json();
            })
            .then(function (json) {
                self.on_config_ok(json);
            })
            .catch(function (error) {
                self.on_config_error(error);
            });
    }

    on_config_ok(json) {
        this.print_debug('on_config_ok()');
        this.on_create_connection(json);
    }

    on_config_error(error) {
        this.print_error('on_config_error()', error);
        this.on_create_connection(this.default_config);
    }

    on_create_connection(config) {
        this.print_debug('on_create_connection()', JSON.stringify(config));
        this.pc = new RTCPeerConnection(config);

        // Connect audio / video
        self = this;
        this.pc.addEventListener('track', function(event) {
            self.on_track(event);
        });

        this.negotiate();
    }

    negotiate() {
        this.print_debug('negotiate()');

        this.pc.addTransceiver('video', {direction: 'recvonly'});
        if (this.audio_object) {
            this.pc.addTransceiver('audio', {direction: 'recvonly'});
        }

        self = this;
        return this.pc.createOffer().then(function(offer) {
            return self.pc.setLocalDescription(offer);
        }).then(function() {
            // wait for ICE gathering to complete
            return new Promise(function(resolve) {
                if (self.pc.iceGatheringState === 'complete') {
                    resolve();
                } else {
                    function checkState() {
                        if (self.pc.iceGatheringState === 'complete') {
                            self.pc.removeEventListener('icegatheringstatechange', checkState);
                            resolve();
                        }
                    }
                    self.pc.addEventListener('icegatheringstatechange', checkState);
                }
            });
        }).then(function() {
            var offer = self.pc.localDescription;
            return fetch('/offer', {
                body: JSON.stringify({
                    sdp: offer.sdp,
                    type: offer.type,
                }),
                headers: {
                    'Content-Type': 'application/json'
                },
                method: 'POST'
            });
        }).then(function(response) {
            return response.json();
        }).then(function(answer) {
            return self.pc.setRemoteDescription(answer);
        }).catch(function(e) {
            alert(e);
        });
    }

    on_track(event) {
        this.print_debug('on_track()');
        if (event.track.kind == 'video') {
            this.video_object.srcObject = event.streams[0];
        } else if (event.track.kind == 'audio') {
            this.audio_object.srcObject = event.streams[0];
        }
    }
}

function negotiate()
{
    pc.addTransceiver('video', {direction: 'recvonly'});
    // pc.addTransceiver('audio', {direction: 'recvonly'});

    return pc.createOffer().then(function(offer) {
        return pc.setLocalDescription(offer);
    }).then(function() {
        // wait for ICE gathering to complete
        return new Promise(function(resolve) {
            if (pc.iceGatheringState === 'complete') {
                resolve();
            } else {
                function checkState() {
                    if (pc.iceGatheringState === 'complete') {
                        pc.removeEventListener('icegatheringstatechange', checkState);
                        resolve();
                    }
                }
                pc.addEventListener('icegatheringstatechange', checkState);
            }
        });
    }).then(function() {
        var offer = pc.localDescription;
        return fetch('/offer', {
            body: JSON.stringify({
                sdp: offer.sdp,
                type: offer.type,
            }),
            headers: {
                'Content-Type': 'application/json'
            },
            method: 'POST'
        });
    }).then(function(response) {
        return response.json();
    }).then(function(answer) {
        return pc.setRemoteDescription(answer);
    }).catch(function(e) {
        alert(e);
    });
}

function on_start()
{
    print_log('on_start()')

    var config = {
        sdpSemantics: 'unified-plan'
    };

    config.iceServers = [{urls: ['stun:stun.l.google.com:19302']}];

    pc = new RTCPeerConnection(config);

    // connect audio / video
    pc.addEventListener('track', function(evt) {
        if (evt.track.kind == 'video') {
            document.getElementById('rtc-realtime-video').srcObject = evt.streams[0];
        } else {
            // document.getElementById('audio').srcObject = evt.streams[0];
        }
    });

    negotiate();
}

function on_stop()
{
    print_log('on_stop()')

    // close peer connection
    setTimeout(function() {
        pc.close();
    }, 500);
}

var default_video_client = new RealTimeVideoClient('client', 'rtc-realtime-video')
window.addEventListener('load', function(event) {
    default_video_client.start();
})
window.addEventListener('unload', function(event) {
    default_video_client.stop();
    default_video_client = null;
})
