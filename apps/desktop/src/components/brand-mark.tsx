import { cn } from '@/lib/utils'

const assetPath = (path: string) => `${import.meta.env.BASE_URL}${path.replace(/^\/+/, '')}`

// FOOL-SEAM: brand-mark
// Marka rozeti: The Fool jester işareti (kullanıcının kendi marka varlığı).
// Upstream burada `nous-girl.jpg` gösteriyordu.
//
// Şeffaf zeminli PNG olduğu için upstream'in beyaz karosu kaldırıldı —
// jester zaten kendi silüetiyle duruyor ve beyaz karo koyu temada kutu
// gibi görünüyordu.
//
// Hakkında ekranında ve güncelleme panelinde görünür.
export function BrandMark({ className, ...props }: React.ComponentProps<'span'>) {
  return (
    <span
      className={cn('inline-flex size-14 shrink-0 items-center justify-center overflow-hidden rounded-md', className)}
      {...props}
    >
      <img alt="" className="size-full object-contain" src={assetPath('fool-mark.png')} />
    </span>
  )
}
