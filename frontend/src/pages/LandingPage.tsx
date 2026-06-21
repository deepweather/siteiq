/**
 * LandingPage — public marketing surface.
 *
 * Visual hierarchy mirrors the dashboard so the funnel feels coherent:
 *  - Orange primary, JetBrains Mono for big numbers, generous whitespace.
 *  - Hero: a hard claim ("€81K/month walks off your jobsite") plus a
 *    live counter that ticks up while you read.
 *  - Three "Observe → Quantify → Prescribe" cards.
 *  - Interactive ROI slider — proves the math personalizes.
 *  - Quote / social-proof slot.
 *  - CTA card with two prominent buttons.
 */
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { LiveWasteCounter } from '../components/landing/LiveWasteCounter';

const LOCALE = 'en-DE';

function fmtEUR(n: number, digits = 0): string {
  return new Intl.NumberFormat(LOCALE, {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: digits,
  }).format(n);
}

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <Header />
      <Hero />
      <HowItWorks />
      <ROISection />
      <ProofSection />
      <CTASection />
      <Footer />
    </div>
  );
}

function Header() {
  return (
    <header className="px-8 lg:px-16 py-6 flex items-center justify-between sticky top-0 z-10 backdrop-blur bg-background/80 border-b border-border">
      <Link to="/" className="flex items-center gap-2">
        <span className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center">
          <span className="text-primary-foreground text-base font-bold">S</span>
        </span>
        <span className="font-semibold tracking-tight">SiteIQ</span>
      </Link>
      <nav className="hidden md:flex items-center gap-6 text-sm text-muted-foreground">
        <a href="#how" className="hover:text-foreground">How it works</a>
        <a href="#roi" className="hover:text-foreground">ROI</a>
        <a href="#proof" className="hover:text-foreground">Why it works</a>
      </nav>
      <div className="flex items-center gap-3">
        <Link
          to="/login"
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          Sign in
        </Link>
        <Link
          to="/signup"
          className="text-sm bg-primary text-primary-foreground font-semibold rounded-md px-3.5 py-2 hover:bg-primary/90"
        >
          Start free trial
        </Link>
      </div>
    </header>
  );
}

function Hero() {
  return (
    <section className="px-8 lg:px-16 pt-16 lg:pt-24 pb-12 grid lg:grid-cols-12 gap-10 items-end">
      <div className="lg:col-span-7">
        <div className="inline-flex items-center gap-2 rounded-full border border-border px-3 py-1 text-xs text-muted-foreground mb-6">
          <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
          Live simulation across 3 German jobsites
        </div>
        <h1 className="text-5xl lg:text-6xl font-semibold tracking-tight leading-[1.05] mb-6">
          €81,000 / month walks off your jobsite.
          <br />
          <span className="text-muted-foreground">Quietly.</span>
        </h1>
        <p className="text-lg text-muted-foreground max-w-xl mb-8">
          Construction sites are productive only ~35% of the time. SiteIQ uses
          cameras + computer vision to observe everything that moves,
          translate the waste into euros, and prescribe specific operational
          fixes — in real time.
        </p>
        <div className="flex flex-col sm:flex-row gap-3">
          <Link
            to="/signup"
            className="rounded-md bg-primary text-primary-foreground font-semibold text-sm px-5 py-3 hover:bg-primary/90"
          >
            Start a workspace — free for 14 days
          </Link>
          <Link
            to="/login"
            className="rounded-md border border-border font-semibold text-sm px-5 py-3 hover:bg-muted"
          >
            See it on a live site
          </Link>
        </div>
      </div>
      <div className="lg:col-span-5">
        <div className="rounded-xl border border-border bg-card p-6">
          <div className="text-xs uppercase tracking-widest text-muted-foreground font-semibold">
            Recoverable waste, live
          </div>
          <div className="mt-3 font-mono text-5xl font-semibold tabular-nums tracking-tight text-foreground">
            <LiveWasteCounter perDayEUR={3700} />
          </div>
          <p className="text-sm text-muted-foreground mt-3">
            being burnt across simulated SiteIQ sites since you opened this page.
            That's <span className="text-foreground font-medium">€3,700/day</span>{' '}
            on a typical mid-size project.
          </p>
        </div>
      </div>
    </section>
  );
}

function HowItWorks() {
  const cards = [
    {
      title: 'Observe',
      kicker: '01',
      body: "Cameras and YOLO-class CV models track every worker, machine, and material on site. No new hardware needed beyond the cameras you already have.",
    },
    {
      title: 'Quantify',
      kicker: '02',
      body: "Walks become minutes. Minutes become euros. Idle equipment becomes a daily cost of fuel + lease + crew. Everything maps to a number.",
    },
    {
      title: 'Prescribe',
      kicker: '03',
      body: "Move the toilet 30m closer to the foundation crew. Restage the rebar at the gate-side edge of the column zone. Release the second pump for the next 4 hours.",
    },
  ];
  return (
    <section id="how" className="px-8 lg:px-16 py-20 border-t border-border">
      <h2 className="text-3xl font-semibold tracking-tight mb-2">How SiteIQ works</h2>
      <p className="text-muted-foreground mb-12 max-w-2xl">
        Three layers, one number. Every minute, every euro, every fix.
      </p>
      <div className="grid md:grid-cols-3 gap-6">
        {cards.map((c) => (
          <div key={c.title} className="rounded-xl border border-border bg-card p-6">
            <div className="font-mono text-xs text-primary mb-4">{c.kicker}</div>
            <div className="text-xl font-semibold mb-2">{c.title}</div>
            <p className="text-muted-foreground text-sm leading-relaxed">{c.body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

const HOURLY_RATE = 50; // €/h fully loaded
const PRODUCTIVE_FRACTION = 0.35;
const RECOVERABLE_FRACTION = 0.55; // matches RECOVERABLE_WASTE_FRACTION on backend

function ROISection() {
  const [workers, setWorkers] = useState(60);
  const [sites, setSites] = useState(3);

  const monthlyWaste = useMemo(() => {
    // Worker waste = workers × non-productive-fraction × hourly rate × 11h × 22 working days
    const perSite = workers * (1 - PRODUCTIVE_FRACTION) * HOURLY_RATE * 11 * 22;
    return perSite * sites;
  }, [workers, sites]);
  const monthlySavings = monthlyWaste * RECOVERABLE_FRACTION;
  const annualSavings = monthlySavings * 12;
  const cost = sites * 2000; // €2k/site/month — same number as in WasteReport
  const payback = monthlySavings / Math.max(cost, 1);

  return (
    <section id="roi" className="px-8 lg:px-16 py-20 border-t border-border bg-muted/30">
      <h2 className="text-3xl font-semibold tracking-tight mb-2">What it's worth, for your sites.</h2>
      <p className="text-muted-foreground mb-10 max-w-2xl">
        Slide. We do the math.
      </p>
      <div className="grid lg:grid-cols-2 gap-10 items-start">
        <div className="space-y-6">
          <Slider
            label="Workers per site"
            min={20}
            max={200}
            step={5}
            value={workers}
            onChange={setWorkers}
            display={`${workers}`}
          />
          <Slider
            label="Sites"
            min={1}
            max={20}
            step={1}
            value={sites}
            onChange={setSites}
            display={`${sites}`}
          />
        </div>
        <div className="rounded-xl border border-border bg-card p-6">
          <div className="grid grid-cols-2 gap-6">
            <Stat label="Monthly recoverable" value={fmtEUR(monthlySavings)} />
            <Stat label="Annual recoverable" value={fmtEUR(annualSavings)} />
            <Stat label="System cost / month" value={fmtEUR(cost)} />
            <Stat
              label="Payback ratio"
              value={`${payback.toFixed(0)}×`}
              hint="for every €1 spent"
            />
          </div>
          <div className="mt-6 text-xs text-muted-foreground leading-relaxed">
            Based on a 35% baseline productivity rate and a 55% recovery
            after applying SiteIQ recommendations — the centre of the
            40–65% range we observe across project types.
          </div>
        </div>
      </div>
    </section>
  );
}

function Slider({
  label,
  min,
  max,
  step,
  value,
  onChange,
  display,
}: {
  label: string;
  min: number;
  max: number;
  step: number;
  value: number;
  onChange: (v: number) => void;
  display: string;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between mb-2">
        <span className="text-sm font-medium">{label}</span>
        <span className="font-mono tabular-nums text-2xl font-semibold">{display}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-primary"
      />
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-widest text-muted-foreground font-semibold">
        {label}
      </div>
      <div className="font-mono text-3xl font-semibold tabular-nums tracking-tight mt-1">
        {value}
      </div>
      {hint && <div className="text-xs text-muted-foreground mt-1">{hint}</div>}
    </div>
  );
}

function ProofSection() {
  return (
    <section id="proof" className="px-8 lg:px-16 py-20 border-t border-border">
      <div className="grid lg:grid-cols-2 gap-12 items-start">
        <div>
          <h2 className="text-3xl font-semibold tracking-tight mb-4">
            Replaces what you already pay for. Quietly.
          </h2>
          <p className="text-muted-foreground leading-relaxed mb-6">
            SiteIQ subsumes your BauWatch perimeter feeds, your PPE compliance
            tool, and the half-baked Buildots dashboard your project manager
            never opens — and adds the thing they actually wanted: a clear,
            euro-denominated picture of where the day went.
          </p>
          <ul className="space-y-3 text-sm">
            {[
              'YOLO + per-camera calibration — no extra hardware',
              'Live waste in € per zone, equipment, and worker',
              'Recommendations apply with one click and animate on the map',
              'Owner / Admin / Member / Viewer roles with audit log',
            ].map((line) => (
              <li key={line} className="flex items-start gap-3">
                <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-primary shrink-0" />
                <span>{line}</span>
              </li>
            ))}
          </ul>
        </div>
        <blockquote className="rounded-xl border border-border bg-card p-8">
          <p className="text-lg leading-relaxed">
            "We thought we had a productivity problem. Turns out we had a
            walking problem, an idle-crane problem, and a logistics problem.
            SiteIQ separated them and put a euro on each."
          </p>
          <footer className="mt-6 text-sm text-muted-foreground">
            — Site manager, residential project, Berlin
          </footer>
        </blockquote>
      </div>
    </section>
  );
}

function CTASection() {
  return (
    <section className="px-8 lg:px-16 py-20 border-t border-border">
      <div className="rounded-2xl border border-border bg-card p-10 lg:p-14 text-center">
        <h2 className="text-3xl lg:text-4xl font-semibold tracking-tight mb-4">
          See your jobsite in euros.
        </h2>
        <p className="text-muted-foreground max-w-xl mx-auto mb-8">
          Spin up a workspace in under a minute. Live demo simulation
          included. No credit card.
        </p>
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link
            to="/signup"
            className="rounded-md bg-primary text-primary-foreground font-semibold text-sm px-6 py-3 hover:bg-primary/90"
          >
            Start free trial
          </Link>
          <Link
            to="/login"
            className="rounded-md border border-border font-semibold text-sm px-6 py-3 hover:bg-muted"
          >
            Sign in
          </Link>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="px-8 lg:px-16 py-10 border-t border-border text-xs text-muted-foreground flex flex-col md:flex-row gap-4 items-center justify-between">
      <div>© 2026 SiteIQ — Construction site intelligence.</div>
      <div className="flex items-center gap-6">
        <a href="#" className="hover:text-foreground">Privacy</a>
        <a href="#" className="hover:text-foreground">Terms</a>
        <a href="#" className="hover:text-foreground">Contact</a>
      </div>
    </footer>
  );
}
