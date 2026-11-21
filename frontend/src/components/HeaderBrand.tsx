import { IS_DEMO_MODE } from "../api";

/** Логотип, название и метка демо-режима. */
export default function HeaderBrand() {
  return (
    <div className="app-header__brand">
      <img
        src={`${import.meta.env.BASE_URL}logo_shield.png`}
        alt="Логотип Синоникс"
        className="app-header__logo"
      />

      <div className="app-header__titles">
        <span className="app-header__title">
          <span className="app-header__title-full">
            ИИ-ассистент по размещению «Синоникса»
          </span>

          <span className="app-header__title-short">
            ИИ-ассистент «Синоникс»
          </span>
        </span>

        <span className="app-header__subtitle">
          Расчёт правил обмена между двумя сетями
        </span>
      </div>

      {IS_DEMO_MODE && (
        <span
          className="app-header__demo"
          title="Демо-версия: ответы формируются по готовым сценариям, без сервера и ключей ИИ"
        >
          демо
        </span>
      )}
    </div>
  );
}
