# 045 · 차량 안에서 검출된 번호판 후보 이미지를 Windows 한국어 OCR로 읽습니다.
# 표준 입력의 Base64 PNG를 한 장씩 판독해 041로 문자를 돌려줍니다.
# 041은 프레임마다 받은 문자로 번호판 후보가 일치하는지 검사합니다.
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.DataWriter, Windows.Storage.Streams, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Foundation, ContentType=WindowsRuntime]
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -like 'IAsyncOperation*' } | Select-Object -First 1
function Await-Result($Operation, $Type) {
  $task = $asTask.MakeGenericMethod($Type).Invoke($null, @($Operation))
  $task.Wait()
  return $task.Result
}
$ocr = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('ko'))
if ($null -eq $ocr) { throw 'Korean OCR language missing' }
while ($line = [Console]::ReadLine()) {
  $stream = [Windows.Storage.Streams.InMemoryRandomAccessStream]::new()
  $writer = [Windows.Storage.Streams.DataWriter]::new($stream)
  $writer.WriteBytes([Convert]::FromBase64String($line))
  $null = Await-Result ($writer.StoreAsync()) ([UInt32])
  $null = $writer.DetachStream()
  $stream.Seek(0)
  $decoder = Await-Result ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
  $bitmap = Await-Result ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
  $result = Await-Result ($ocr.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
  [Console]::WriteLine($result.Text)
  $bitmap.Dispose()
  $stream.Dispose()
}
