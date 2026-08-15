import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  BadgeCheck,
  BrainCircuit,
  CheckCircle2,
  Cpu,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  Lock,
  LockKeyhole,
  Mail,
  ScanSearch,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  User,
  X,
  Zap,
} from 'lucide-react';
import {
  clearRememberedEmail,
  forgotPassword,
  getRememberedEmail,
  initialsOf,
  resetPassword,
  setRememberedEmail,
  setSession,
  signInWithEmail,
  signUpWithEmail,
  type AuthUser,
} from '../auth';

type Mode = 'signin' | 'signup';
type Stage = 'main' | 'forgot' | 'forgot-sent' | 'forgot-reset' | 'forgot-done';
type BusyKind = 'email' | null;

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

const FEATURES = [
  { icon: ScanSearch, title: 'AI-powered OCR', desc: 'Digital and scanned documents parsed with ~99% accuracy in under a second.' },
  { icon: BrainCircuit, title: 'Smart classification', desc: 'Resumes, CNICs, degrees and transcripts auto-sorted by the LLM engine.' },
  { icon: ShieldCheck, title: 'Instant verification', desc: 'Tamper checks, duplicates and missing documents flagged before upload.' },
  { icon: Zap, title: 'One-pass pipeline', desc: 'Upload a batch once — OCR, extract, verify and report in a single pass.' },
];

const PIPELINE = [
  { icon: Cpu, label: 'Upload' },
  { icon: ScanSearch, label: 'OCR' },
  { icon: BrainCircuit, label: 'Classify' },
  { icon: BadgeCheck, label: 'Verify' },
];

const TICKER = [
  { ok: true, text: 'Resume classified · 98.7% confidence' },
  { ok: true, text: 'CNIC verified · 96.2% confidence' },
  { ok: true, text: 'Degree tamper-check passed' },
  { ok: false, text: 'Duplicate batch flagged instantly' },
  { ok: true, text: 'Transcript OCR · 0.8s elapsed' },
  { ok: true, text: 'Verification report generated · PDF' },
];

const STATS = [
  { value: '99.2%', label: 'OCR accuracy' },
  { value: '1.1s', label: 'Avg processing' },
  { value: '4.2k', label: 'Docs verified' },
];

interface LoginPageProps {
  onAuthed: (user: AuthUser) => void;
}

function mulberry32(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export default function LoginPage({ onAuthed }: LoginPageProps) {
  const [mode, setMode] = useState<Mode>('signin');
  const [stage, setStage] = useState<Stage>('main');
  const [email, setEmail] = useState(() => getRememberedEmail());
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [caps, setCaps] = useState(false);
  const [remember, setRemember] = useState(() => Boolean(getRememberedEmail()));
  const [agree, setAgree] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<BusyKind>(null);
  const [success, setSuccess] = useState<AuthUser | null>(null);
  const [shake, setShake] = useState(false);
  const [newPass, setNewPass] = useState('');
  const [confirmPass, setConfirmPass] = useState('');
  const [resetToken, setResetToken] = useState('');
  const [forgotLink, setForgotLink] = useState('');

  const [featureIdx, setFeatureIdx] = useState(0);
  const [tickerIdx, setTickerIdx] = useState(0);
  const [progress, setProgress] = useState(0);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get('token');
    if (token) {
      setResetToken(token);
      setStage('forgot-reset');
    }
  }, []);

  useEffect(() => {
    timers.current.push(window.setInterval(() => setFeatureIdx((i) => (i + 1) % FEATURES.length), 3200));
    timers.current.push(window.setInterval(() => setTickerIdx((i) => (i + 1) % TICKER.length), 2800));
    timers.current.push(
      window.setInterval(() => setProgress((p) => {
        if (p >= 100) return 0;
        return Math.min(100, p + 2.5);
      }), 80),
    );
    return () => {
      timers.current.forEach((t) => window.clearInterval(t));
      timers.current = [];
    };
  }, []);

  const particles = useMemo(() => {
    const rnd = mulberry32(20260814);
    return Array.from({ length: 46 }, (_, i) => ({
      left: rnd() * 100,
      top: rnd() * 100,
      size: 2 + rnd() * 3.5,
      delay: rnd() * 12,
      duration: 10 + rnd() * 14,
      color: i % 3 === 0 ? 'violet' : i % 3 === 1 ? 'cyan' : 'pink',
    }));
  }, []);

  const feature = FEATURES[featureIdx];
  const FeatureIcon = feature.icon;
  const tick = TICKER[tickerIdx];

  const commitAuth = useCallback(
    (user: AuthUser, token?: string) => {
      if (remember) setRememberedEmail(user.email);
      else clearRememberedEmail();
      setSession(user, token);
      timers.current.push(window.setTimeout(() => onAuthed(user), 1500));
    },
    [remember, onAuthed],
  );

  const validate = (): Record<string, string> => {
    const e: Record<string, string> = {};
    const em = email.trim();
    if (!em) e.email = 'Email is required.';
    else if (!EMAIL_RE.test(em)) e.email = 'Enter a valid email address.';

    if (mode === 'signin') {
      if (!password) e.password = 'Password is required.';
    } else {
      if (!name.trim()) e.name = 'Full name is required.';
      else if (name.trim().length < 2) e.name = 'Name looks too short.';
      if (!password) e.password = 'Create a password.';
      else if (password.length < 8) e.password = 'Use at least 8 characters.';
      if (confirm !== password) e.confirm = 'Passwords do not match.';
      if (!agree) e.agree = 'Please accept the Terms to continue.';
    }
    return e;
  };

  const submitEmail = async (ev?: React.FormEvent) => {
    ev?.preventDefault();
    if (busy || success) return;
    if (stage !== 'main') return;
    const e = validate();
    setErrors(e);
    if (Object.keys(e).length > 0) {
      setShake(true);
      timers.current.push(window.setTimeout(() => setShake(false), 500));
      return;
    }
    setBusy('email');
    try {
      const res = mode === 'signin' ? await signInWithEmail(email, password) : await signUpWithEmail(email, name, password);
      if (!res.ok || !res.user) {
        setErrors({ form: res.error ?? 'Something went wrong. Please try again.' });
        setShake(true);
        timers.current.push(window.setTimeout(() => setShake(false), 500));
        return;
      }
      setSuccess(res.user);
      commitAuth(res.user, res.token);
    } finally {
      setBusy(null);
    }
  };

  const submitForgot = async (ev?: React.FormEvent) => {
    ev?.preventDefault();
    const em = email.trim();
    if (!EMAIL_RE.test(em)) {
      setErrors({ email: 'Enter a valid email address.' });
      return;
    }
    setErrors({});
    setBusy('email');
    const res = await forgotPassword(em);
    setBusy(null);
    if (!res.ok) {
      setErrors({ form: res.error ?? 'Could not process the request. Try again.' });
      return;
    }
    setForgotLink(res.devResetLink ?? '');
    setStage('forgot-sent');
  };

  const submitReset = async (ev?: React.FormEvent) => {
    ev?.preventDefault();
    const e: Record<string, string> = {};
    if (!newPass) e.newPass = 'Create a new password.';
    else if (newPass.length < 8) e.newPass = 'Use at least 8 characters.';
    if (confirmPass !== newPass) e.confirmPass = 'Passwords do not match.';
    setErrors(e);
    if (Object.keys(e).length > 0) return;
    if (!resetToken) {
      setErrors({ form: 'This reset link is missing its token. Request a new reset link.' });
      return;
    }
    setBusy('email');
    const res = await resetPassword(resetToken, newPass);
    setBusy(null);
    if (!res.ok) {
      setErrors({ form: res.error ?? 'Could not reset the password. Try again.' });
      return;
    }
    setStage('forgot-done');
  };

  const startForgot = () => {
    setNewPass('');
    setConfirmPass('');
    setErrors({});
    setForgotLink('');
    setStage('forgot');
  };

  const strength = useMemo(() => {
    let score = 0;
    if (password.length >= 8) score++;
    if (password.length >= 12) score++;
    if (/[A-Z]/.test(password) && /[a-z]/.test(password)) score++;
    if (/\d/.test(password)) score++;
    if (/[^A-Za-z0-9]/.test(password)) score++;
    const labels = ['Very weak', 'Weak', 'Fair', 'Good', 'Strong', 'Excellent'];
    const colors = ['var(--rose)', 'var(--rose)', 'var(--amber)', 'var(--amber)', 'var(--emerald)', 'var(--emerald)'];
    return { score: Math.min(5, score), label: labels[Math.min(5, score)], color: colors[Math.min(5, score)] };
  }, [password]);

  const clearError = (k: string) => setErrors((prev) => ({ ...prev, [k]: '' }));

  const inputError = (k: string) => (errors[k] ? 'input-error' : '');

  return (
    <div className="login-page">
      <div className="login-grid" />
      <div className="login-orb orb-a" />
      <div className="login-orb orb-b" />
      <div className="login-orb orb-c" />
      <div className="login-particles" aria-hidden="true">
        {particles.map((p, i) => (
          <span
            key={i}
            className={`pdot pd-${p.color}`}
            style={{
              left: `${p.left}%`,
              top: `${p.top}%`,
              width: p.size,
              height: p.size,
              animationDelay: `${p.delay}s`,
              animationDuration: `${p.duration}s`,
            }}
          />
        ))}
      </div>

      <div className="login-layout">
        <section className="login-showcase">
          <div className="showcase-inner">
            <div className="brand lg-brand">
              <div className="logo lg-logo">EEF</div>
              <div>
                <h1>Verity.AI</h1>
                <div className="tag">Intelligent Document Verification Engine</div>
              </div>
            </div>

            <div className="showcase-glow" />

            <div className="showcase-head">
              <div className="eyebrow"><Sparkles size={13} /> AI-004 · Ezitech Engineering Framework</div>
              <h2>
                Verify documents in{' '}
                <span className="grad-text">seconds</span>,
                <br />
                not days.
              </h2>
              <p>
                The IDP engine reads, classifies and verifies internship application
                documents — resumes, CNICs, degrees and transcripts — automatically.
              </p>
            </div>

            <div className="showcase-feature" key={featureIdx}>
              <div className="sf-icon"><FeatureIcon size={20} /></div>
              <div>
                <div className="sf-title">{feature.title}</div>
                <div className="sf-desc">{feature.desc}</div>
              </div>
              <div className="sf-dots">
                {FEATURES.map((_, i) => (
                  <span key={i} className={i === featureIdx ? 'on' : ''} />
                ))}
              </div>
            </div>

            <div className="pipeline">
              <div className="pipeline-track">
                <div className="pipeline-fill" style={{ width: `${progress}%` }} />
                <div className="pipeline-dot" style={{ left: `calc(${progress}% - 5px)` }} />
              </div>
              <div className="pipeline-nodes">
                {PIPELINE.map((n, i) => {
                  const NIcon = n.icon;
                  const on = progress >= ((i + 1) / PIPELINE.length) * 100;
                  return (
                    <div key={n.label} className={`p-node ${on ? 'on' : ''}`}>
                      <div className="p-node-icon"><NIcon size={15} /></div>
                      <span>{n.label}</span>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="ticker">
              <div className="ticker-label">live pipeline</div>
              <div className="ticker-row" key={tickerIdx}>
                {tick.ok ? <CheckCircle2 size={14} /> : <ShieldAlert size={14} />}
                <span>{tick.text}</span>
              </div>
            </div>

            <div className="stats">
              {STATS.map((s) => (
                <div key={s.label} className="stat">
                  <div className="stat-value">{s.value}</div>
                  <div className="stat-label">{s.label}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="login-form-side">
          <div className={`login-card ${shake ? 'shake' : ''}`}>
            {success ? (
              <div className="success-wrap">
                <div className="success-ring">
                  <div className="success-check"><CheckCircle2 size={44} /></div>
                </div>
                <h2>Welcome aboard</h2>
                <p className="success-name">{success.name}</p>
                <p className="muted">Authenticating secure session…</p>
              </div>
            ) : stage === 'forgot-done' ? (
              <div className="forgot-done">
                <div className="forgot-icon"><KeyRound size={26} /></div>
                <h2>Password updated</h2>
                <p className="muted">
                  Your password has been reset. Sign in with your new password.
                </p>
                <button className="btn block" onClick={() => setStage('main')}>
                  <ArrowRight size={16} /> Back to sign in
                </button>
              </div>
            ) : stage === 'forgot' ? (
              <div className="forgot-panel">
                <button className="link-back" onClick={() => { setStage('main'); clearError('email'); }}>
                  <ArrowLeft size={14} /> Back to sign in
                </button>
                <div className="forgot-icon"><KeyRound size={26} /></div>
                <h2>Reset your password</h2>
                <p className="muted">Enter your account email to continue.</p>
                <form onSubmit={submitForgot} noValidate>
                  <div className="field">
                    <label htmlFor="femail">Email address</label>
                    <div className="input-wrap">
                      <Mail size={16} />
                      <input
                        id="femail"
                        type="email"
                        placeholder="you@example.com"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        autoComplete="email"
                        autoFocus
                      />
                    </div>
                    {errors.email && <div className="field-error"><AlertCircle size={13} /> {errors.email}</div>}
                  </div>
                  <button className="btn block" type="submit" disabled={busy === 'email'}>
                    {busy === 'email' ? <><Loader2 size={16} className="spin" /> Sending…</> : <><KeyRound size={16} /> Continue</>}
                  </button>
                </form>
              </div>
            ) : stage === 'forgot-sent' ? (
              <div className="forgot-panel">
                <button className="link-back" onClick={() => { setStage('main'); clearError('email'); }}>
                  <ArrowLeft size={14} /> Back to sign in
                </button>
                <div className="forgot-icon"><KeyRound size={26} /></div>
                <h2>Check your email</h2>
                <p className="muted">
                  If that email is registered, a password reset link has been sent to <b>{email.trim()}</b>.
                </p>
                {forgotLink && (
                  <div style={{ marginTop: 12, padding: '12px 14px', background: 'rgba(34,211,238,0.08)', border: '1px solid rgba(34,211,238,0.3)', borderRadius: 12 }}>
                    <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>Email not configured — development reset link:</div>
                    <a className="link-btn" href={forgotLink} style={{ wordBreak: 'break-all' }}>{forgotLink}</a>
                  </div>
                )}
                <button className="btn block" onClick={() => setStage('main')}>
                  <ArrowRight size={16} /> Back to sign in
                </button>
              </div>
            ) : stage === 'forgot-reset' ? (
              <div className="forgot-panel">
                <button className="link-back" onClick={() => { setStage('forgot'); clearError('form'); }}>
                  <ArrowLeft size={14} /> Back
                </button>
                <div className="forgot-icon"><KeyRound size={26} /></div>
                <h2>Choose a new password</h2>
                <p className="muted">Enter a new password for your account.</p>
                <form onSubmit={submitReset} noValidate>
                  <div className="field">
                    <label htmlFor="npass">New password</label>
                    <div className={`input-wrap ${inputError('newPass')}`}>
                      <Lock size={16} />
                      <input
                        id="npass"
                        type={showPass ? 'text' : 'password'}
                        placeholder="At least 8 characters"
                        value={newPass}
                        onChange={(e) => { setNewPass(e.target.value); clearError('newPass'); }}
                        autoComplete="new-password"
                        autoFocus
                      />
                    </div>
                    {errors.newPass && <div className="field-error"><AlertCircle size={13} /> {errors.newPass}</div>}
                  </div>
                  <div className="field">
                    <label htmlFor="cpass">Confirm new password</label>
                    <div className={`input-wrap ${inputError('confirmPass')}`}>
                      <LockKeyhole size={16} />
                      <input
                        id="cpass"
                        type={showPass ? 'text' : 'password'}
                        placeholder="Repeat your new password"
                        value={confirmPass}
                        onChange={(e) => { setConfirmPass(e.target.value); clearError('confirmPass'); }}
                        autoComplete="new-password"
                      />
                    </div>
                    {errors.confirmPass && <div className="field-error"><AlertCircle size={13} /> {errors.confirmPass}</div>}
                  </div>
                  {errors.form && <div className="form-error"><AlertCircle size={14} /> {errors.form}</div>}
                  <button className="btn block" type="submit" disabled={busy === 'email'}>
                    {busy === 'email' ? <><Loader2 size={16} className="spin" /> Updating…</> : <><KeyRound size={16} /> Update password</>}
                  </button>
                </form>
              </div>
            ) : (
              <>
                <div className="tabs">
                  <button
                    type="button"
                    className={`tab ${mode === 'signin' ? 'active' : ''}`}
                    onClick={() => { setMode('signin'); setErrors({}); }}
                  >
                    Sign in
                  </button>
                  <button
                    type="button"
                    className={`tab ${mode === 'signup' ? 'active' : ''}`}
                    onClick={() => { setMode('signup'); setErrors({}); }}
                  >
                    Create account
                  </button>
                </div>

                <div className="card-head">
                  <h2>{mode === 'signin' ? 'Welcome back' : 'Create your account'}</h2>
                  <p className="muted">
                    {mode === 'signin'
                      ? 'Sign in to access the verification command center.'
                      : 'Start verifying applicant documents in minutes.'}
                  </p>
                </div>

                <form onSubmit={submitEmail} noValidate>
                  {mode === 'signup' && (
                    <div className="field">
                      <label htmlFor="name">Full name</label>
                      <div className="input-wrap">
                        <User size={16} />
                        <input
                          id="name"
                          type="text"
                          placeholder="Jane Doe"
                          value={name}
                          onChange={(e) => { setName(e.target.value); clearError('name'); }}
                          autoComplete="name"
                          autoFocus
                        />
                      </div>
                      {errors.name && <div className="field-error"><AlertCircle size={13} /> {errors.name}</div>}
                    </div>
                  )}

                  <div className="field">
                    <label htmlFor="email">Email address</label>
                    <div className={`input-wrap ${inputError('email')}`}>
                      <Mail size={16} />
                      <input
                        id="email"
                        type="email"
                        placeholder="you@example.com"
                        value={email}
                        onChange={(e) => { setEmail(e.target.value); clearError('email'); }}
                        autoComplete="email"
                        autoFocus={mode === 'signin'}
                      />
                    </div>
                    {errors.email && <div className="field-error"><AlertCircle size={13} /> {errors.email}</div>}
                  </div>

                  <div className="field">
                    <label htmlFor="password">Password</label>
                    <div className={`input-wrap ${inputError('password')}`}>
                      <Lock size={16} />
                      <input
                        id="password"
                        type={showPass ? 'text' : 'password'}
                        placeholder={mode === 'signin' ? 'Enter your password' : 'At least 8 characters'}
                        value={password}
                        onChange={(e) => { setPassword(e.target.value); clearError('password'); clearError('confirm'); }}
                        onKeyDown={(e) => setCaps(e.getModifierState('CapsLock'))}
                        autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
                      />
                      <button
                        type="button"
                        className="eye-btn"
                        tabIndex={-1}
                        onClick={() => setShowPass((s) => !s)}
                        aria-label={showPass ? 'Hide password' : 'Show password'}
                      >
                        {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
                      </button>
                    </div>
                    {errors.password && <div className="field-error"><AlertCircle size={13} /> {errors.password}</div>}
                    {caps && (
                      <div className="caps-warning"><LockKeyhole size={13} /> Caps Lock is on</div>
                    )}
                    {mode === 'signup' && password.length > 0 && (
                      <div className="strength">
                        <div className="strength-bars">
                          {Array.from({ length: 5 }, (_, i) => (
                            <span
                              key={i}
                              style={{
                                background: i < strength.score ? strength.color : 'rgba(255,255,255,0.08)',
                              }}
                            />
                          ))}
                        </div>
                        <span style={{ color: strength.color }}>{strength.label}</span>
                      </div>
                    )}
                  </div>

                  {mode === 'signup' && (
                    <div className="field">
                      <label htmlFor="confirm">Confirm password</label>
                      <div className={`input-wrap ${inputError('confirm')}`}>
                        <LockKeyhole size={16} />
                        <input
                          id="confirm"
                          type={showPass ? 'text' : 'password'}
                          placeholder="Repeat your password"
                          value={confirm}
                          onChange={(e) => { setConfirm(e.target.value); clearError('confirm'); }}
                          autoComplete="new-password"
                        />
                      </div>
                      {errors.confirm && <div className="field-error"><AlertCircle size={13} /> {errors.confirm}</div>}
                    </div>
                  )}

                  {mode === 'signin' ? (
                    <div className="form-row">
                      <label className="checkbox">
                        <input
                          type="checkbox"
                          checked={remember}
                          onChange={(e) => setRemember(e.target.checked)}
                        />
                        <span className="checkmark" />
                        Remember me
                      </label>
                      <button type="button" className="link-btn" onClick={startForgot}>
                        Forgot password?
                      </button>
                    </div>
                  ) : (
                    <div className="form-row">
                      <label className="checkbox">
                        <input type="checkbox" checked={agree} onChange={(e) => { setAgree(e.target.checked); clearError('agree'); }} />
                        <span className="checkmark" />
                        <span>
                          I agree to the <a href="#" onClick={(e) => e.preventDefault()}>Terms</a> &amp; <a href="#" onClick={(e) => e.preventDefault()}>Privacy Policy</a>
                        </span>
                      </label>
                    </div>
                  )}

                  {errors.form && <div className="form-error"><AlertCircle size={14} /> {errors.form}</div>}
                  {errors.agree && <div className="field-error"><AlertCircle size={13} /> {errors.agree}</div>}

                  <button className="btn block submit" type="submit" disabled={busy !== null}>
                    {busy === 'email' ? (
                      <><Loader2 size={17} className="spin" /> {mode === 'signin' ? 'Verifying…' : 'Creating account…'}</>
                    ) : (
                      <>
                        {mode === 'signin' ? 'Secure sign in' : 'Create account'}
                        <ArrowRight size={17} />
                      </>
                    )}
                  </button>
                </form>
              </>
            )}
          </div>

          <div className="form-foot">
            <span>EEF v2.1 · AI-004 Case Study</span>
            <span className="dot-sep">·</span>
            <span>Developed by Touseef Abrar</span>
          </div>
        </section>
      </div>

      {success && (
        <div className="success-overlay">
          <div className="success-glow" />
          <div className="success-card">
            <div className="success-avatar">
              {initialsOf(success.name)}
              <span className="success-badge"><BadgeCheck size={14} /></span>
            </div>
            <div className="success-title">Session secured</div>
            <div className="success-email">{success.email}</div>
            <div className="success-bar"><div /></div>
            <div className="success-sub">Redirecting to command center…</div>
          </div>
        </div>
      )}

      <div className="login-close" aria-hidden="true">
        <X size={16} />
      </div>
    </div>
  );
}
