// Draws a shareable "Certificate of Clean Segregation" for a Bhawan and downloads it as a PNG.
"use strict";

async function downloadCertificate({ bhawan, score, rank, of, days }) {
  try { await document.fonts.ready; } catch { /* fonts API missing: system fonts are fine */ }
  const W = 1600, H = 1130;
  const c = document.createElement("canvas");
  c.width = W; c.height = H;
  const g = c.getContext("2d");
  const ink = "#1d2a4b", pen = "#c8323c", pass = "#1f8a55", warn = "#c3850c";
  const grade = score >= 80 ? "A" : score >= 60 ? "B" : "C";
  const stampColor = { A: pass, B: warn, C: pen }[grade];

  // paper with ruled lines and a red margin
  g.fillStyle = "#f8fafd"; g.fillRect(0, 0, W, H);
  g.strokeStyle = "#dbe5f1"; g.lineWidth = 2;
  for (let y = 60; y < H; y += 44) { g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke(); }
  g.strokeStyle = "#eba5ab"; g.lineWidth = 3;
  g.beginPath(); g.moveTo(130, 0); g.lineTo(130, H); g.stroke();

  // double border
  g.strokeStyle = ink; g.lineWidth = 6; g.strokeRect(50, 50, W - 100, H - 100);
  g.lineWidth = 2; g.strokeRect(68, 68, W - 136, H - 136);

  // four bins, top centre
  const binColors = ["#2e8b57", "#2563a8", "#9b2c5a", "#d39b00"];
  binColors.forEach((col, i) => {
    const x = W / 2 - 110 + i * 56, y = 120;
    g.fillStyle = col;
    g.fillRect(x, y + 10, 40, 8);
    g.fillRect(x + 13, y + 3, 14, 7);
    g.beginPath(); g.moveTo(x + 4, y + 22); g.lineTo(x + 36, y + 22); g.lineTo(x + 32, y + 62); g.lineTo(x + 8, y + 62); g.closePath(); g.fill();
  });

  g.textAlign = "center";
  g.fillStyle = ink;
  g.font = '800 64px "Baloo 2", system-ui, sans-serif';
  g.fillText("Certificate of Clean Segregation", W / 2, 265);
  g.font = '400 30px "Hind", system-ui, sans-serif';
  g.fillStyle = "#55607e";
  g.fillText("Kachra Report Card, IIT Roorkee", W / 2, 315);

  g.fillStyle = ink;
  g.font = '400 34px "Hind", system-ui, sans-serif';
  g.fillText("This is to certify that", W / 2, 420);
  g.font = '800 110px "Baloo 2", system-ui, sans-serif';
  g.fillText(`${bhawan} Bhawan`, W / 2, 545);

  g.font = '400 34px "Hind", system-ui, sans-serif';
  const period = days === 1 ? "today" : `over the last ${days} days`;
  g.fillText(`kept its bins separated with a score of ${score}/100 ${period},`, W / 2, 625);
  g.fillText(`ranking ${ordinal(rank)} of ${of} Bhawans on campus.`, W / 2, 675);

  // teacher's remark in red pen
  g.fillStyle = pen;
  g.font = '700 46px "Kalam", "Segoe Print", cursive';
  const remark = grade === "A" ? "Excellent. Keep it up!" : grade === "B" ? "Good effort, aim for A!" : "Room to improve. Next week!";
  g.fillText(remark, W / 2, 790);

  // stamp
  g.save();
  g.translate(W - 290, H - 280); g.rotate(-0.17);
  g.strokeStyle = stampColor; g.fillStyle = stampColor;
  g.lineWidth = 10; g.beginPath(); g.arc(0, 0, 120, 0, Math.PI * 2); g.stroke();
  g.lineWidth = 4; g.beginPath(); g.arc(0, 0, 100, 0, Math.PI * 2); g.stroke();
  g.font = '800 150px "Baloo 2", system-ui, sans-serif'; g.textBaseline = "middle";
  g.fillText(grade, 0, 10);
  g.restore();

  // date + signature line
  g.textAlign = "left"; g.textBaseline = "alphabetic";
  g.fillStyle = ink; g.font = '400 28px "Hind", system-ui, sans-serif';
  const date = new Date().toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" });
  g.fillText(date, 190, H - 170);
  g.strokeStyle = ink; g.lineWidth = 2;
  g.beginPath(); g.moveTo(190, H - 215); g.lineTo(560, H - 215); g.stroke();
  g.fillStyle = "#55607e"; g.font = '400 24px "Hind", system-ui, sans-serif';
  g.fillText("Graded under the Solid Waste Management Rules 2026", 190, H - 130);

  const blob = await new Promise((res) => c.toBlob(res, "image/png"));
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: `${bhawan}-bhawan-certificate.png` });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

function ordinal(n) {
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}
