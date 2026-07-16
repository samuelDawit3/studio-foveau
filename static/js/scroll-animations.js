document.addEventListener('DOMContentLoaded', () => {
    const heroVideo = document.getElementById('hero-video');

    if (heroVideo) {
        heroVideo.muted = true;
        heroVideo.defaultMuted = true;
        heroVideo.volume = 0;

        const tryPlay = () => {
            const playPromise = heroVideo.play();

            if (playPromise !== undefined) {
                playPromise.catch(() => {
                    // Do not display controls or a play button.
                });
            }
        };

        if (heroVideo.readyState >= 2) {
            tryPlay();
        } else {
            heroVideo.addEventListener('canplay', tryPlay, { once: true });
        }

        document.addEventListener('visibilitychange', () => {
            if (!document.hidden && heroVideo.paused) {
                tryPlay();
            }
        });
    }

    const elements = document.querySelectorAll('.scroll-animate');

    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        elements.forEach((element) => element.classList.add('visible'));
        return;
    }

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.1 });

    elements.forEach(element => observer.observe(element));
});
