(function () {
    function initMobileNav(options) {
        const config = Object.assign(
            {
                breakpoint: 900,
                bodyClass: 'mobile-nav-enabled',
                openClass: 'nav-open',
                toggleSelector: '#mobileNavToggle',
                overlaySelector: '#mobileNavOverlay',
                sidebarSelector: '#sidebarNav',
                navLinksSelector: '#sidebarNav .nav-links a'
            },
            options || {}
        );

        const body = document.body;
        if (!body || !body.classList.contains(config.bodyClass)) {
            return;
        }

        function applyIPhoneViewportScale() {
            const viewportMeta = document.querySelector('meta[name="viewport"]');
            if (!viewportMeta) {
                return;
            }

            const userAgent = navigator.userAgent || '';
            const isIPhone = /iPhone/i.test(userAgent);
            const isCompactWidth = window.innerWidth <= 600;

            if (!viewportMeta.dataset.defaultContent) {
                viewportMeta.dataset.defaultContent =
                    viewportMeta.getAttribute('content') || 'width=device-width, initial-scale=1.0';
            }

            if (isIPhone && isCompactWidth) {
                viewportMeta.setAttribute(
                    'content',
                    'width=device-width, initial-scale=0.8, viewport-fit=cover'
                );
                body.classList.add('iphone-compact-view');
                return;
            }

            viewportMeta.setAttribute('content', viewportMeta.dataset.defaultContent);
            body.classList.remove('iphone-compact-view');
        }

        applyIPhoneViewportScale();

        const toggle = document.querySelector(config.toggleSelector);
        const overlay = document.querySelector(config.overlaySelector);
        const sidebar = document.querySelector(config.sidebarSelector);
        if (!toggle || !overlay || !sidebar) {
            return;
        }

        if (toggle.dataset.mobileNavBound === 'true') {
            return;
        }
        toggle.dataset.mobileNavBound = 'true';

        function setOpen(isOpen) {
            body.classList.toggle(config.openClass, isOpen);
            toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
        }

        function close() {
            setOpen(false);
        }

        toggle.addEventListener('click', function () {
            setOpen(!body.classList.contains(config.openClass));
        });

        overlay.addEventListener('click', close);

        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape' && body.classList.contains(config.openClass)) {
                close();
            }
        });

        window.addEventListener('resize', function () {
            applyIPhoneViewportScale();
            if (window.innerWidth > config.breakpoint && body.classList.contains(config.openClass)) {
                close();
            }
        });

        const navLinks = document.querySelectorAll(config.navLinksSelector);
        navLinks.forEach(function (link) {
            link.addEventListener('click', function () {
                if (window.innerWidth <= config.breakpoint) {
                    close();
                }
            });
        });
    }

    window.initMobileNav = initMobileNav;
})();
