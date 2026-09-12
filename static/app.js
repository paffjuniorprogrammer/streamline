const form = document.querySelector('#url-form');
const video = document.querySelector('#video-player');
const status = document.querySelector('#video-status');
const overlay = document.querySelector('#video-overlay');

if (form) {
    form.addEventListener('submit', () => {
        const button = document.querySelector('#play-button');
        button.disabled = true;
        button.querySelector('span').textContent = 'Loading';
    });
}

if (video) {
    const serverStream = video.dataset.streamUrl.startsWith('/stream?');
    let serverSeek = false;
    let ignoreSeekUntil = 0;
    let seekTimer;

    video.addEventListener('seeking', () => {
        if (!serverStream || serverSeek || Date.now() < ignoreSeekUntil || video.currentTime < 1) {
            return;
        }

        clearTimeout(seekTimer);
        const target = video.currentTime;
        seekTimer = setTimeout(() => {
            serverSeek = true;
            ignoreSeekUntil = Date.now() + 1500;
            video.dataset.targetTime = target;
            status.textContent = 'Seeking...';
            video.src = `${video.dataset.streamUrl}&start=${encodeURIComponent(target)}`;
            video.load();
            video.play().catch(() => {});
        }, 350);
    });

    video.addEventListener('loadedmetadata', () => {
        if (!serverSeek) return;
        video.currentTime = Number(video.dataset.targetTime);
        delete video.dataset.targetTime;
        setTimeout(() => { serverSeek = false; }, 250);
    });

    video.addEventListener('canplay', () => {
        status.textContent = 'Ready to play.';
        overlay.classList.add('ready');
        video.closest('.player-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    video.addEventListener('waiting', () => {
        status.textContent = 'Buffering...';
        overlay.classList.remove('ready');
    });
    video.addEventListener('playing', () => {
        status.textContent = 'Playing.';
        overlay.classList.add('ready');
    });

}
