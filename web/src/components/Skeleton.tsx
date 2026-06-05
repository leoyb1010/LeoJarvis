// 统一的加载占位骨架：所有 view 在数据到达前共用，替代裸文字 loading，消除毛坯感。

export function SkelLine({ w = "100%", h = 12 }: { w?: string | number; h?: number }) {
  return <span className="skeleton skel-line" style={{ width: typeof w === "number" ? `${w}px` : w, height: h }} />;
}

export function SkelCard({ lines = 3 }: { lines?: number }) {
  return (
    <div className="card skel-card">
      <SkelLine w={84} h={11} />
      <SkelLine w="62%" h={22} />
      <div className="skel-rows">
        {Array.from({ length: lines }).map((_, i) => (
          <SkelLine key={i} w={`${88 - i * 12}%`} h={11} />
        ))}
      </div>
    </div>
  );
}

export function PageSkeleton({ cards = 6, hero = true, head = true }: { cards?: number; hero?: boolean; head?: boolean }) {
  return (
    <div className="page-skeleton" aria-busy="true" aria-label="加载中">
      {head ? (
        <div className="skel-head">
          <SkelLine w={140} h={12} />
          <SkelLine w="46%" h={34} />
          <SkelLine w="68%" h={14} />
        </div>
      ) : null}
      {hero ? (
        <div className="skel-hero-grid">
          <SkelCard lines={3} />
          <SkelCard lines={4} />
          <SkelCard lines={3} />
        </div>
      ) : null}
      <div className="skel-grid">
        {Array.from({ length: cards }).map((_, i) => (
          <SkelCard key={i} lines={2 + (i % 3)} />
        ))}
      </div>
    </div>
  );
}
