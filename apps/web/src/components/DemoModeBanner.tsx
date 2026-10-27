export function DemoModeBanner({ visible }: { visible: boolean }) {
  if (!visible) return null
  return <div className="demo-banner" role="status"><strong>Demo mode</strong><span>Values come from sanitized local fixtures. Live portal behavior is unverified.</span></div>
}
