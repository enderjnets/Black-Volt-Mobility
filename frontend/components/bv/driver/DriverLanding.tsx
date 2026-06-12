"use client";

/* Driver subscription landing (driver.blackvoltmobility.com). Faithful port of
   frontend/driver-landing.html into React: hero, value props, 3-tier pricing
   (Free → app signup, Operator → checkout modal with monthly/annual toggle,
   Growth → sales email), trust band, footer. Bilingual via useI18n. */

import { useState } from "react";

import { useI18n } from "@/lib/i18n";
import { DriverCheckout } from "./DriverCheckout";
import "./driver.css";

const APP_URL = process.env.NEXT_PUBLIC_APP_URL || "https://app.blackvoltmobility.com/dashboard";
const SALES_EMAIL = process.env.NEXT_PUBLIC_SALES_EMAIL || "hola@blackvoltmobility.com";

function Check() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#00E5FF"
      strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 13l4 4L19 7" />
    </svg>
  );
}

function Clock() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  );
}

export function DriverLanding() {
  const { t, lang, setLang } = useI18n();
  const [checkout, setCheckout] = useState(false);
  const [annual, setAnnual] = useState(false);

  const planKey = annual ? "operator_annual" : "operator";
  const priceLabel = annual ? t("driver.op.priceAnnual") : t("driver.op.priceMonthly");
  const growthHref = `mailto:${SALES_EMAIL}?subject=${encodeURIComponent("Growth - Black Volt")}`;

  return (
    <div className="bv-driver" id="top">
      <nav className="bv-nav">
        <div className="bv-wrap">
          <a className="bv-brand" href="#top">
            <svg className="bv-bolt" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M13 2 L5 13 H11 L10 22 L19 9 H13 Z" fill="#00E5FF" />
            </svg>
            <span className="bv-wm">BLACK VOLT</span>
          </a>
          <div className="bv-navlinks">
            <a href="#planes">{t("driver.nav.plans")}</a>
            <a href={APP_URL}>{t("driver.nav.signin")}</a>
            <span className="bv-lang bv-langwrap">
              <button className={lang === "en" ? "on" : ""} onClick={() => setLang("en")}>EN</button>
              <button className={lang === "es" ? "on" : ""} onClick={() => setLang("es")}>ES</button>
            </span>
            <a className="bv-btn cyan" href="#planes">{t("driver.nav.viewPlans")}</a>
          </div>
        </div>
      </nav>

      <header className="bv-header">
        <div className="bv-wrap">
          <div className="bv-hline" />
          <div className="bv-eyebrow">{t("driver.hero.eyebrow")}</div>
          <h1>
            {t("driver.hero.titlePre")} <span className="hl">{t("driver.hero.titleHl")}</span>
            {t("driver.hero.titlePost")}
          </h1>
          <p className="bv-sub">{t("driver.hero.sub")}</p>
          <div className="bv-herocta">
            <a className="bv-btn cyan" href="#planes">{t("driver.hero.ctaPlans")}</a>
            <a className="bv-btn" href="#como">{t("driver.hero.ctaHow")}</a>
          </div>
          <div className="bv-tag">⚡ <span>{t("driver.hero.tag")}</span></div>
        </div>
      </header>

      <section id="como">
        <div className="bv-wrap bv-props">
          {(["1", "2", "3"] as const).map((i) => (
            <div className="bv-prop" key={i}>
              <div className="ic">{i === "1" ? "⚡" : i === "2" ? "🛡" : "📈"}</div>
              <h3>{t(`driver.prop${i}.title`)}</h3>
              <p>{t(`driver.prop${i}.desc`)}</p>
            </div>
          ))}
        </div>
      </section>

      <section id="planes" className="bv-pricing">
        <div className="bv-wrap">
          <span className="bv-eyebrow">{t("driver.pricing.eyebrow")}</span>
          <h2>{t("driver.pricing.title")}</h2>
          <p className="bv-lead">{t("driver.pricing.lead")}</p>

          <div className="bv-billtoggle" role="tablist" aria-label="billing period">
            <button className={annual ? "" : "on"} onClick={() => setAnnual(false)}>
              {t("driver.bill.monthly")}
            </button>
            <button className={annual ? "on" : ""} onClick={() => setAnnual(true)}>
              {t("driver.bill.annual")}
            </button>
          </div>

          <div className="bv-tiers">
            {/* Free */}
            <div className="bv-tier">
              <div className="nm">{t("driver.free.name")}</div>
              <div className="tg">{t("driver.free.tag")}</div>
              <div className="bv-price"><span className="n">$0</span><span className="u">{t("driver.bill.perMonth")}</span></div>
              <div className="bv-submeta">{t("driver.free.forever")}</div>
              <ul className="bv-feat" style={{ marginTop: 18 }}>
                {["1", "2", "3", "4"].map((n) => (
                  <li key={n}><Check />{t(`driver.free.f${n}`)}</li>
                ))}
              </ul>
              <div className="cta">
                <a className="bv-btn block" href={APP_URL}>{t("driver.free.cta")}</a>
                <div className="bv-lockline">🔒 {t("driver.free.lock")}</div>
              </div>
            </div>

            {/* Operator */}
            <div className="bv-tier rec">
              <span className="bv-badge">{t("driver.op.badge")}</span>
              <div className="nm">{t("driver.op.name")}</div>
              <div className="tg">{t("driver.op.tag")}</div>
              <div className="bv-price">
                <span className="n cy">{annual ? "$290" : "$29"}</span>
                <span className="u">{annual ? t("driver.bill.perYear") : t("driver.bill.perMonth")}</span>
              </div>
              <div className="bv-submeta">
                {annual ? t("driver.op.subAnnual") : t("driver.op.subMonthly")}
              </div>
              <div className="bv-inc">{t("driver.op.inc")}</div>
              <ul className="bv-feat">
                {["1", "2", "3", "4", "5"].map((n) => (
                  <li key={n}><Check />{t(`driver.op.f${n}`)}</li>
                ))}
              </ul>
              <div className="cta">
                <button className="bv-btn cyan block" onClick={() => setCheckout(true)}>
                  {t("driver.op.cta")}
                </button>
              </div>
            </div>

            {/* Growth */}
            <div className="bv-tier">
              <div className="nm">{t("driver.growth.name")}</div>
              <div className="tg">{t("driver.growth.tag")}</div>
              <div className="bv-price"><span className="n">$79</span><span className="u">{t("driver.growth.unit")}</span></div>
              <div className="bv-submeta">{t("driver.growth.sub")}</div>
              <div className="bv-inc">{t("driver.growth.inc")}</div>
              <ul className="bv-feat">
                {["1", "2", "3"].map((n) => (
                  <li key={n}><Check />{t(`driver.growth.f${n}`)}</li>
                ))}
                <li className="soon"><Clock />{t("driver.growth.f4")}</li>
              </ul>
              <div className="cta">
                <a className="bv-btn block" href={growthHref}>{t("driver.growth.cta")}</a>
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="bv-trust">
        <div className="bv-wrap">
          <span>✓ <b>{t("driver.trust1")}</b></span>
          <span>✓ <b>{t("driver.trust2a")}</b> {t("driver.trust2b")}</span>
          <span>✓ {t("driver.trust3a")} <b>Square</b></span>
          <span>✓ <b>{t("driver.trust4")}</b></span>
        </div>
      </div>

      <footer className="bv-footer">
        <div className="bv-wrap">
          <div><b>Black Volt Mobility LLC</b> · Denver / Aurora, CO</div>
          <div>{t("brand.tagline")}</div>
        </div>
      </footer>

      <DriverCheckout
        open={checkout}
        onClose={() => setCheckout(false)}
        planKey={planKey}
        priceLabel={priceLabel}
        salesEmail={SALES_EMAIL}
      />
    </div>
  );
}
