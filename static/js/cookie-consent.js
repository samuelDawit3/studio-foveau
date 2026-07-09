document.addEventListener('DOMContentLoaded', () => {
    const banner = document.getElementById('cookie-consent-banner');
    const acceptBtn = document.getElementById('cookie-accept');
    const declineBtn = document.getElementById('cookie-decline');
    const STORAGE_KEY = 'studiofoveau_cookie_consent';

    if (!banner || !acceptBtn || !declineBtn) {
        return;
    }

    const savedChoice = localStorage.getItem(STORAGE_KEY);
    if (!savedChoice) {
        banner.hidden = false;
    }

    const saveChoice = (value) => {
        localStorage.setItem(STORAGE_KEY, value);
        banner.hidden = true;
    };

    acceptBtn.addEventListener('click', () => saveChoice('accepted'));
    declineBtn.addEventListener('click', () => saveChoice('declined'));
});
