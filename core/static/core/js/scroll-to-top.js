document.addEventListener('DOMContentLoaded', function() {
    const scrollButton = document.querySelector('.scroll-to-top');
    if (!scrollButton) return;

    // Более плавное появление
    function handleScroll() {
        if (window.scrollY > 300) {
            scrollButton.classList.add('visible');
        } else {
            scrollButton.classList.remove('visible');
        }
    }

    // Задержка для плавности
    let isScrolling;
    window.addEventListener('scroll', function() {
        window.clearTimeout(isScrolling);
        isScrolling = setTimeout(handleScroll, 50);
    }, false);

    // Плавная прокрутка с easing
    scrollButton.addEventListener('click', function(e) {
        e.preventDefault();
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    });

    // Инициализация при загрузке
    handleScroll();
});