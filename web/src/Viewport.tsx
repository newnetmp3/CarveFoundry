import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import type { DesignShape, PocketPreview, PocketSettings, Stock } from './types';

interface Props {
  stock: Stock;
  shapes: DesignShape[];
  selectedId: string | null;
  pocket: PocketSettings;
  preview: PocketPreview | null;
  onSelect: (id: string | null) => void;
}

export function Viewport({ stock, shapes, selectedId, pocket, preview, onSelect }: Props) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x111a18);
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 12000);
    camera.up.set(0, 0, 1);
    camera.position.set(stock.widthMm * 0.92, -stock.heightMm * 1.35, stock.widthMm * 0.85);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    element.appendChild(renderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.target.set(stock.widthMm / 2, stock.heightMm / 2, -stock.thicknessMm / 4);
    controls.update();

    scene.add(new THREE.AmbientLight(0xffffff, 1.4));
    const light = new THREE.DirectionalLight(0xffffff, 2.6);
    light.position.set(-60, -80, 220);
    scene.add(light);
    const stockMesh = new THREE.Mesh(
      new THREE.BoxGeometry(stock.widthMm, stock.heightMm, stock.thicknessMm),
      new THREE.MeshStandardMaterial({ color: 0xb69b75, roughness: 0.9 })
    );
    stockMesh.position.set(stock.widthMm / 2, stock.heightMm / 2, -stock.thicknessMm / 2);
    scene.add(stockMesh);

    const grid = new THREE.GridHelper(
      Math.max(stock.widthMm, stock.heightMm) * 1.7, 24, 0x42675d, 0x28443d
    );
    grid.rotation.x = Math.PI / 2;
    grid.position.set(stock.widthMm / 2, stock.heightMm / 2, -stock.thicknessMm - 0.2);
    scene.add(grid);
    const origin = new THREE.AxesHelper(25);
    origin.position.set(0, 0, 0.3);
    scene.add(origin);

    const shapeMeshes: THREE.Mesh[] = [];
    for (const item of shapes) {
      const shape = new THREE.Shape();
      if (item.kind === 'rectangle') {
        shape.moveTo(item.xMm, item.yMm);
        shape.lineTo(item.xMm + item.widthMm, item.yMm);
        shape.lineTo(item.xMm + item.widthMm, item.yMm + item.heightMm);
        shape.lineTo(item.xMm, item.yMm + item.heightMm);
        shape.closePath();
      } else {
        shape.absellipse(
          item.xMm + item.widthMm / 2, item.yMm + item.heightMm / 2,
          item.widthMm / 2, item.heightMm / 2, 0, Math.PI * 2, false, 0
        );
      }
      const mesh = new THREE.Mesh(
        new THREE.ExtrudeGeometry(shape, { depth: 1.8, bevelEnabled: false, curveSegments: 48 }),
        new THREE.MeshStandardMaterial({
          color: selectedId === item.id ? 0x6be0a7 : 0x237956,
          roughness: 0.6, transparent: true, opacity: 0.92,
        })
      );
      mesh.userData.shapeId = item.id;
      shapeMeshes.push(mesh);
      scene.add(mesh);
    }

    // The dashed boundary is ONLY a demonstration pocket region, not a valid machining envelope.
    const boundary = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(pocket.xMm, pocket.yMm, 2.5),
      new THREE.Vector3(pocket.xMm + pocket.widthMm, pocket.yMm, 2.5),
      new THREE.Vector3(pocket.xMm + pocket.widthMm, pocket.yMm + pocket.heightMm, 2.5),
      new THREE.Vector3(pocket.xMm, pocket.yMm + pocket.heightMm, 2.5),
    ]);
    const outline = new THREE.LineLoop(boundary, new THREE.LineDashedMaterial({
      color: 0xf6bc70, dashSize: 4, gapSize: 2, depthTest: false,
    }));
    outline.computeLineDistances();
    outline.renderOrder = 15;
    scene.add(outline);

    if (preview) {
      const cutting: number[] = [];
      const traveling: number[] = [];
      for (let index = 1; index < preview.moves.length; index++) {
        const previous = preview.moves[index - 1];
        const current = preview.moves[index];
        const array = current.kind === 'cut' || current.kind === 'plunge' ? cutting : traveling;
        array.push(previous.xMm, previous.yMm, previous.zMm + 0.15,
          current.xMm, current.yMm, current.zMm + 0.15);
      }
      for (const [positions, color] of [[cutting, 0x6df4b0], [traveling, 0x7e9fff]] as const) {
        const geom = new THREE.BufferGeometry();
        geom.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
        const lines = new THREE.LineSegments(geom,
          new THREE.LineBasicMaterial({ color, depthTest: false, transparent: true, opacity: 0.83 }));
        lines.renderOrder = 20;
        scene.add(lines);
      }
    }

    const ray = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const handleSelect = (event: MouseEvent) => {
      if (event.button !== 0) return;
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1,
        -((event.clientY - rect.top) / rect.height) * 2 + 1);
      ray.setFromCamera(pointer, camera);
      const hit = ray.intersectObjects(shapeMeshes, false)[0];
      onSelect(hit ? String(hit.object.userData.shapeId) : null);
    };
    renderer.domElement.addEventListener('click', handleSelect);

    const resize = () => {
      const width = Math.max(element.clientWidth, 1);
      const height = Math.max(element.clientHeight, 1);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    resize();

    let frame = 0;
    const draw = () => {
      controls.update();
      renderer.render(scene, camera);
      frame = requestAnimationFrame(draw);
    };
    draw();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      renderer.domElement.removeEventListener('click', handleSelect);
      controls.dispose();
      scene.traverse((object) => {
        const mesh = object as THREE.Mesh;
        if (mesh.geometry) mesh.geometry.dispose();
        if (mesh.material) {
          const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
          for (const material of materials) material.dispose();
        }
      });
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [stock, shapes, selectedId, pocket, preview, onSelect]);

  return <div ref={host} className="viewport" aria-label="Interactive three-dimensional stock and design preview" />;
}
