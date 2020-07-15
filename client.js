const prefix = '[rtc.realtime_video.client.on_start] '
var pc = null;

function print_log(... args)
{
    console.log(prefix, ... args);
}

function print_error(... args)
{
    console.error(prefix, ... args);
}

function get_ices()
{
    return fetch('/ices', {method: 'GET'})
        .then(function (response) {
            return response.json();
        })
        .then(function (json) {
            print_log(JSON.stringify(json));
        });
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

window.addEventListener('load', function(e) {
    on_start(e)
})
window.addEventListener('unload', function(e) {
    on_stop(e)
})
