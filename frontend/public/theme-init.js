// Инициализация темы до первой отрисовки.
//
// Вынесено из index.html в отдельный файл: инлайновый скрипт —
// потенциальная XSS-поверхность и блокируется политикой CSP.
// Скрипт подключается обычным <script> без defer, поэтому
// выполняется до первой отрисовки — вспышки светлой темы нет.

(function () {
  try {
    var stored = localStorage.getItem("synonyx:theme");
    var mode =
      stored === "dark" || stored === "light"
        ? stored
        : window.matchMedia("(prefers-color-scheme: dark)").matches
          ? "dark"
          : "light";

    document.documentElement.dataset.theme = mode;
    document.documentElement.style.colorScheme = mode;

    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute("content", mode === "dark" ? "#070707" : "#FFFFFF");
    }
  } catch (error) {
    /* приватный режим браузера может запрещать localStorage */
  }
})();
