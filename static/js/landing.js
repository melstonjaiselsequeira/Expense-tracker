/**
 * ExpenseFlow — Premium Landing Page Interactive Scripts
 * Features:
 *  - Sticky Navbar Blur & Shadow on Scroll
 *  - Accessible Mobile Hamburger Drawer Menu
 *  - Offset Smooth Scrolling for Section Links
 *  - ScrollSpy Navigation Highlighting
 *  - Progressive IntersectionObserver Staggered Scroll Reveal
 *  - Interactive Dashboard Preview Tab Switcher
 *  - Accessible Contact, Privacy & Terms Modals
 */

document.addEventListener('DOMContentLoaded', () => {
  initNavbarScroll();
  initMobileMenu();
  initSmoothScroll();
  initScrollSpy();
  initScrollReveal();
  initShowcaseTabs();
  initModals();
  initContactForm();
});

/* ── 1. Sticky Navbar on Scroll ─────────────────────────────── */
function initNavbarScroll() {
  const navbar = document.getElementById('navbar-wrapper');
  if (!navbar) return;

  const onScroll = () => {
    if (window.scrollY > 20) {
      navbar.classList.add('scrolled');
    } else {
      navbar.classList.remove('scrolled');
    }
  };

  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
}

/* ── 2. Mobile Hamburger Drawer Menu ────────────────────────── */
function initMobileMenu() {
  const menuBtn = document.getElementById('mobile-menu-btn');
  const drawer = document.getElementById('mobile-nav-drawer');

  if (!menuBtn || !drawer) return;

  const toggleDrawer = (open) => {
    const shouldOpen = open !== undefined ? open : !drawer.classList.contains('open');
    drawer.classList.toggle('open', shouldOpen);
    menuBtn.classList.toggle('active', shouldOpen);
    menuBtn.setAttribute('aria-expanded', shouldOpen ? 'true' : 'false');
    drawer.setAttribute('aria-hidden', shouldOpen ? 'false' : 'true');
  };

  menuBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    toggleDrawer();
  });

  // Close drawer when clicking any link inside
  drawer.querySelectorAll('a').forEach((link) => {
    link.addEventListener('click', () => {
      toggleDrawer(false);
    });
  });

  // Close when clicking outside
  document.addEventListener('click', (e) => {
    if (drawer.classList.contains('open') && !drawer.contains(e.target) && !menuBtn.contains(e.target)) {
      toggleDrawer(false);
    }
  });

  // Close on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && drawer.classList.contains('open')) {
      toggleDrawer(false);
    }
  });
}

/* ── 3. Smooth Scrolling with Sticky Nav Offset ─────────────── */
function initSmoothScroll() {
  const links = document.querySelectorAll('a[href^="#"]');
  const headerHeight = 85;

  links.forEach((link) => {
    link.addEventListener('click', (e) => {
      const targetId = link.getAttribute('href');
      if (targetId === '#' || !targetId) return;

      const targetEl = document.querySelector(targetId);
      if (targetEl) {
        e.preventDefault();
        const elementPosition = targetEl.getBoundingClientRect().top;
        const offsetPosition = elementPosition + window.pageYOffset - headerHeight;

        window.scrollTo({
          top: offsetPosition,
          behavior: 'smooth'
        });

        // Update URL hash without jumping
        if (history.pushState) {
          history.pushState(null, null, targetId);
        }
      }
    });
  });
}

/* ── 4. ScrollSpy Navigation Highlighting ───────────────────── */
function initScrollSpy() {
  const sections = document.querySelectorAll('section[id]');
  const desktopLinks = document.querySelectorAll('.desktop-nav .nav-item');
  const mobileLinks = document.querySelectorAll('.mobile-nav-link');

  if (sections.length === 0) return;

  const onScroll = () => {
    const scrollPosition = window.scrollY + 140;

    sections.forEach((section) => {
      const sectionTop = section.offsetTop;
      const sectionHeight = section.offsetHeight;
      const sectionId = section.getAttribute('id');

      if (scrollPosition >= sectionTop && scrollPosition < sectionTop + sectionHeight) {
        desktopLinks.forEach((link) => {
          link.classList.toggle('active', link.getAttribute('href') === `#${sectionId}`);
        });

        mobileLinks.forEach((link) => {
          link.classList.toggle('active', link.getAttribute('href') === `#${sectionId}`);
        });
      }
    });
  };

  window.addEventListener('scroll', onScroll, { passive: true });
}

/* ── 5. Staggered Scroll Reveal Animations ──────────────────── */
function initScrollReveal() {
  // If user prefers reduced motion, skip animations
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    return;
  }

  const items = document.querySelectorAll('.reveal-item');
  if (items.length === 0 || !('IntersectionObserver' in window)) return;

  // Add progressive enhancement class
  document.documentElement.classList.add('js-reveal');

  const observer = new IntersectionObserver(
    (entries, obs) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          obs.unobserve(entry.target);
        }
      });
    },
    {
      threshold: 0.05,
      rootMargin: '0px 0px 60px 0px'
    }
  );

  items.forEach((item) => observer.observe(item));
}

/* ── 6. Interactive Dashboard Preview Tabs ──────────────────── */
function initShowcaseTabs() {
  const tabs = document.querySelectorAll('.showcase-tab');
  const tabViews = document.querySelectorAll('.tab-view');

  if (tabs.length === 0 || tabViews.length === 0) return;

  tabs.forEach((tab) => {
    tab.addEventListener('click', () => {
      const targetTabId = tab.getAttribute('data-tab');

      // Update tabs active state
      tabs.forEach((t) => t.classList.remove('active'));
      tab.classList.add('active');

      // Update tab views
      tabViews.forEach((view) => {
        if (view.getAttribute('id') === targetTabId) {
          view.classList.add('active');
        } else {
          view.classList.remove('active');
        }
      });
    });
  });
}

/* ── 7. Modals: Contact, Privacy Policy, Terms ──────────────── */
function initModals() {
  const modalConfigs = [
    {
      backdropId: 'contact-modal',
      openTriggers: ['open-contact-modal'],
      closeTriggers: ['close-contact-modal']
    },
    {
      backdropId: 'privacy-modal',
      openTriggers: ['open-privacy-modal'],
      closeTriggers: ['close-privacy-modal', 'close-privacy-btn']
    },
    {
      backdropId: 'terms-modal',
      openTriggers: ['open-terms-modal'],
      closeTriggers: ['close-terms-modal', 'close-terms-btn']
    }
  ];

  modalConfigs.forEach(({ backdropId, openTriggers, closeTriggers }) => {
    const backdrop = document.getElementById(backdropId);
    if (!backdrop) return;

    const openModal = () => {
      backdrop.classList.add('open');
      backdrop.setAttribute('aria-hidden', 'false');
      document.body.style.overflow = 'hidden';
    };

    const closeModal = () => {
      backdrop.classList.remove('open');
      backdrop.setAttribute('aria-hidden', 'true');
      document.body.style.overflow = '';
    };

    openTriggers.forEach((triggerId) => {
      const btn = document.getElementById(triggerId);
      if (btn) btn.addEventListener('click', openModal);
    });

    closeTriggers.forEach((triggerId) => {
      const btn = document.getElementById(triggerId);
      if (btn) btn.addEventListener('click', closeModal);
    });

    // Close on backdrop click (outside modal dialog)
    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) {
        closeModal();
      }
    });

    // Close on ESC
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && backdrop.classList.contains('open')) {
        closeModal();
      }
    });
  });
}

/* ── 8. Contact Form Handling ───────────────────────────────── */
function initContactForm() {
  const form = document.getElementById('contact-form');
  const alertBox = document.getElementById('contact-feedback');
  const submitBtn = document.getElementById('contact-submit-btn');

  if (!form || !alertBox || !submitBtn) return;

  form.addEventListener('submit', (e) => {
    e.preventDefault();

    const name = document.getElementById('contact-name').value.trim();
    const email = document.getElementById('contact-email').value.trim();
    const message = document.getElementById('contact-message').value.trim();

    if (!name || !email || !message) {
      alertBox.className = 'modal-alert-box error';
      alertBox.textContent = 'Please complete all fields before submitting.';
      alertBox.style.display = 'block';
      return;
    }

    // Submit state animation
    const originalText = submitBtn.innerHTML;
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Sending message...';

    setTimeout(() => {
      form.reset();
      submitBtn.disabled = false;
      submitBtn.innerHTML = originalText;

      alertBox.className = 'modal-alert-box success';
      alertBox.innerHTML = '<i class="fas fa-check-circle"></i> Thank you! Your message has been received. Our team will get back to you shortly.';
      alertBox.style.display = 'block';

      setTimeout(() => {
        alertBox.style.display = 'none';
        const contactModal = document.getElementById('contact-modal');
        if (contactModal) {
          contactModal.classList.remove('open');
          document.body.style.overflow = '';
        }
      }, 2500);
    }, 700);
  });
}
