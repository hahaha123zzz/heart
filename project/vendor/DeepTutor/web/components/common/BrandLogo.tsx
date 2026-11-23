/** 直接展示提供的知学原图，收起导航时只显示图形部分。 */
export default function BrandLogo({compact=false,className=""}:{compact?:boolean;className?:string}) {
  return <svg role="img" aria-label="知学" viewBox={compact?"80 435 530 410":"80 435 1100 410"} className={className}>
    <image href="/zhixue-logo.png" width="1280" height="1280" />
  </svg>;
}
