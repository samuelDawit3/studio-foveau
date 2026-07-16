document.addEventListener('DOMContentLoaded', () => {
    const videos = document.querySelectorAll('.hero-video');
    if (!videos.length) {
        return;
    }

    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    videos.forEach((video) => {
        const wrapper = video.closest('.hero-media-wrap');
        const toggle = wrapper ? wrapper.querySelector('.hero-video-toggle') : null;

        const playLabel = toggle?.dataset.labelPlay || 'Play video';
        const pauseLabel = toggle?.dataset.labelPause || 'Pause video';

        const setToggleState = (isPlaying) => {
            if (!toggle) {
                return;
            }
            const icon = toggle.querySelector('i');
            const hiddenText = toggle.querySelector('.visually-hidden');
            toggle.setAttribute('aria-label', isPlaying ? pauseLabel : playLabel);
            if (hiddenText) {
                hiddenText.textContent = isPlaying ? pauseLabel : playLabel;
            }
            if (icon) {
                icon.classList.toggle('fa-pause', isPlaying);
                icon.classList.toggle('fa-play', !isPlaying);
            }
        };

        const fallbackToPosterImage = () => {
            if (!wrapper) {
                return;
            }
            const img = document.createElement('img');
            img.src = video.poster;
            img.alt = video.getAttribute('aria-label') || '';
            img.title = video.getAttribute('aria-label') || '';
            img.className = video.className;
            img.loading = 'lazy';
            img.decoding = 'async';
            wrapper.replaceChild(img, video);
            if (toggle) {
                toggle.setAttribute('disabled', 'disabled');
            }
        };

        video.addEventListener('error', fallbackToPosterImage);
        const source = video.querySelector('source');
        if (source) {
            source.addEventListener('error', fallbackToPosterImage);
        }

        if (prefersReducedMotion) {
            video.pause();
            video.removeAttribute('autoplay');
            video.currentTime = 0;
            setToggleState(false);
        } else {
            const playAttempt = video.play();
            if (playAttempt && typeof playAttempt.catch === 'function') {
                playAttempt.catch(() => {
                    setToggleState(false);
                });
            }
            setToggleState(true);
        }

        if (toggle) {
            toggle.addEventListener('click', () => {
                if (video.paused) {
                    const playPromise = video.play();
                    if (playPromise && typeof playPromise.catch === 'function') {
                        playPromise.catch(() => {
                            setToggleState(false);
                        });
                    }
                    setToggleState(true);
                } else {
                    video.pause();
                    setToggleState(false);
                }
            });
        }
    });
});
