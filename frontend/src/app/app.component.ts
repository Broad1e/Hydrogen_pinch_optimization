import { Component, ElementRef, ViewChild, AfterViewInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import * as d3 from 'd3';

interface GraphPoint {
  x: number;
  y: number;
}

interface BaselineResponse {
  status: string;
  baseline_fresh_h2: number;
  baseline_curve: GraphPoint[];
  baseline_topology: any[];
}

interface OptimizeResponse {
  status: string;
  method: string;
  is_optimized: boolean;
  message: string;
  baseline_fresh_h2: number;
  optimized_fresh_h2: number;
  saved_h2: number;
  savings_percent: number;
  pinch_point: number | null;
  baseline_curve: GraphPoint[];
  optimized_curve: GraphPoint[];
  new_topology: any[];
}

interface DatasetInfo {
  id: number;
  description: string;
}

interface DatasetsResponse {
  datasets: DatasetInfo[];
}

type OptimizationMethod = 'lp' | 'cascade' | 'mcmf' | 'nlp';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css']
})
export class AppComponent implements AfterViewInit {
  @ViewChild('chart') chartContainer!: ElementRef;

  // Данные для графика
  baselineData: GraphPoint[] = [];
  optimizedData: GraphPoint[] = [];

  // Данные для таблицы
  currentConsumption: number = 0;
  optimizedConsumption: number = 0;
  difference: number = 0;
  isOptimized: boolean = false;
  isLoading: boolean = false;
  isImprovement: boolean = true;
  errorMessage: string = '';

  // Датасеты
  datasets: DatasetInfo[] = [];
  selectedDatasetId: number = 1;

  // Данные для таблиц топологии
  baselineTopologyData: { source_name: string; sink_name: string; flow_amount: number }[] = [];
  topologyData: { source_name: string; sink_name: string; flow_amount: number }[] = [];
  showTopology: boolean = false; // Видимость таблиц топологии

  // Массив методов для кнопок
  methods: OptimizationMethod[] = ['lp', 'cascade', 'mcmf', 'nlp'];
  selectedMethod: OptimizationMethod = 'lp';
  appliedMethod: OptimizationMethod = 'lp';

  private margin = { top: 60, right: 160, bottom: 60, left: 70 };
  private width = 900;
  private height = 500;

  private apiUrl = '/api/v1/pinch';

  constructor(
    private http: HttpClient,
    private cdr: ChangeDetectorRef
  ) {}

  ngAfterViewInit() {
    setTimeout(() => {
      this.loadDatasets();
    }, 100);
  }

  // ============================================
  // ЗАГРУЗКА ДАТАСЕТОВ
  // ============================================
  loadDatasets() {
    this.http.get<DatasetsResponse>(`${this.apiUrl}/datasets`).subscribe({
      next: (res) => {
        this.datasets = res.datasets;
        if (this.datasets.length > 0) {
          this.selectedDatasetId = this.datasets[0].id;
          this.loadBaseline();
        }
      },
      error: (err) => console.error('Ошибка загрузки датасетов:', err)
    });
  }

  // ============================================
  // СМЕНА ДАТАСЕТА
  // ============================================
  changeDataset(event: any) {
    this.selectedDatasetId = Number(event.target.value);
    // При смене датасета сбрасываем оптимизацию и грузим baseline
    this.loadBaseline();
  }

  // ============================================
  // ЗАГРУЗКА BASELINE
  // ============================================
  loadBaseline() {
    this.isLoading = true;
    this.errorMessage = '';
    
    this.http.get<BaselineResponse>(`${this.apiUrl}/baseline?dataset_id=${this.selectedDatasetId}`)
      .subscribe({
        next: (response) => {
          this.baselineData = response.baseline_curve;
          this.currentConsumption = response.baseline_fresh_h2;
          this.baselineTopologyData = response.baseline_topology || [];
          
          this.optimizedData = [];
          this.optimizedConsumption = 0;
          this.difference = 0;
          this.isOptimized = false;
          this.topologyData = [];
          this.showTopology = false;
          this.isLoading = false;
          
          this.cdr.detectChanges();
          this.renderChart();
        },
        error: (error) => {
          console.error('Ошибка загрузки baseline:', error);
          const detail = error.error?.detail || 'Проверьте подключение к бэкенду';
          this.errorMessage = `Ошибка загрузки данных: ${detail}`;
          this.isLoading = false;
          this.cdr.detectChanges();
        }
      });
  }

  // ============================================
  // ОПТИМИЗАЦИЯ
  // ============================================
  optimize() {
    if (this.isLoading) return;
    
    this.isLoading = true;
    this.errorMessage = '';
    this.cdr.detectChanges();

    this.http.get<OptimizeResponse>(
      `${this.apiUrl}/optimize?method=${this.selectedMethod}&dataset_id=${this.selectedDatasetId}`
    ).subscribe({
      next: (response) => {
        this.baselineData = response.baseline_curve;
        this.currentConsumption = response.baseline_fresh_h2;
        
        this.appliedMethod = this.selectedMethod; // Фиксируем метод, которым мы оптимизировали

        this.optimizedData = response.optimized_curve;
        this.optimizedConsumption = response.optimized_fresh_h2;
        this.difference = response.saved_h2;
        this.isImprovement = response.saved_h2 > 0;
        this.isOptimized = true;
        this.topologyData = response.new_topology || [];
        // При новой оптимизации можно оставить топологию открытой, или скрыть. 
        // Оставим как есть: если была открыта - будет открыта.
        this.isLoading = false;
        
        this.cdr.detectChanges();
        this.renderChart();
      },
      error: (error) => {
        console.error('Ошибка оптимизации:', error);
        const detail = error.error?.detail || error.message || 'Неизвестная ошибка';
        this.errorMessage = `Ошибка оптимизации: ${detail}`;
        this.isLoading = false;
        this.cdr.detectChanges();
      }
    });
  }

  // ============================================
  // СМЕНА МЕТОДА
  // ============================================
  changeMethod(method: OptimizationMethod) {
    this.selectedMethod = method;
    // Больше не делаем автоматическую оптимизацию:
    // if (this.isOptimized) { this.optimize(); }
  }

  // ============================================
  // ТОГГЛ ТАБЛИЦЫ
  // ============================================
  toggleTopology() {
    this.showTopology = !this.showTopology;
  }

  // ============================================
  // ОТРИСОВКА ГРАФИКА
  // ============================================
  private renderChart() {
    if (!this.chartContainer) return;

    const container = this.chartContainer.nativeElement;
    container.innerHTML = '';

    const svgWidth = this.width;
    const svgHeight = this.height;
    const innerWidth = svgWidth - this.margin.left - this.margin.right;
    const innerHeight = svgHeight - this.margin.top - this.margin.bottom;

    const svg = d3.select(container)
      .append('svg')
      .attr('width', svgWidth)
      .attr('height', svgHeight)
      .append('g')
      .attr('transform', `translate(${this.margin.left},${this.margin.top})`);

    const allData = [...this.baselineData];
    if (this.optimizedData && this.optimizedData.length > 0) {
      allData.push(...this.optimizedData);
    }

    if (allData.length === 0) {
      svg.append('text')
        .attr('x', innerWidth / 2)
        .attr('y', innerHeight / 2)
        .attr('text-anchor', 'middle')
        .style('fill', '#666')
        .style('font-size', '18px')
        .text('Нет данных для отображения');
      return;
    }

    // ИСПРАВЛЕНО: добавлены типы для параметров
    const maxX = d3.max(allData, (d: GraphPoint) => d.x) || 500;
    const minY = d3.min(allData, (d: GraphPoint) => d.y) || 85;
    const maxY = 101;

    const xScale = d3.scaleLinear()
      .domain([0, maxX * 1.1])
      .range([0, innerWidth]);

    const yScale = d3.scaleLinear()
      .domain([Math.max(80, minY - 2), maxY])
      .range([innerHeight, 0]);

    const xAxis = d3.axisBottom(xScale).ticks(8);
    const yAxis = d3.axisLeft(yScale).ticks(8);

    // Оси
    svg.append('g')
      .attr('transform', `translate(0,${innerHeight})`)
      .call(xAxis)
      .style('color', '#aaa')
      .style('font-size', '12px')
      .append('text')
      .attr('x', innerWidth / 2)
      .attr('y', 40)
      .attr('fill', '#aaa')
      .style('font-size', '14px')
      .style('text-anchor', 'middle')
      .style('font-weight', '500')
      .text('Расход ВСГ, т/сут');

    svg.append('g')
      .call(yAxis)
      .style('color', '#aaa')
      .style('font-size', '12px')
      .append('text')
      .attr('x', -innerHeight / 2)
      .attr('y', -50)
      .attr('fill', '#aaa')
      .style('font-size', '14px')
      .style('text-anchor', 'middle')
      .attr('transform', 'rotate(-90)')
      .style('font-weight', '500')
      .text('Концентрация H₂, %');

    // Сетка
    svg.append('g')
      .attr('class', 'grid')
      .call(d3.axisLeft(yScale).ticks(8).tickSize(-innerWidth).tickFormat(() => ''))
      .style('color', 'rgba(255,255,255,0.05)')
      .style('stroke-dasharray', '4,4');

    // Фильтр свечения
    const defs = svg.append('defs');

    // Clip path — ничего не рисуется за пределами области графика
    defs.append('clipPath')
      .attr('id', 'chart-clip')
      .append('rect')
      .attr('x', 0)
      .attr('y', 0)
      .attr('width', innerWidth)
      .attr('height', innerHeight);

    const filter = defs.append('filter')
      .attr('id', 'glow')
      .attr('x', '-50%')
      .attr('y', '-50%')
      .attr('width', '200%')
      .attr('height', '200%');

    filter.append('feGaussianBlur')
      .attr('stdDeviation', '3')
      .attr('result', 'blur');

    filter.append('feMerge')
      .selectAll('feMergeNode')
      .data(['blur', 'SourceGraphic'])
      .enter()
      .append('feMergeNode')
      .attr('in', (d: string) => d);

    // Функция для рисования линии
    const drawNeonLine = (data: GraphPoint[], color: string, label: string) => {
      if (!data || data.length === 0) return;

      const line = d3.line<GraphPoint>()
        .x((d: GraphPoint) => xScale(d.x))
        .y((d: GraphPoint) => yScale(d.y))
        .curve(d3.curveStepAfter);

      // Группа с clip path — всё рисуется только внутри области графика
      const g = svg.append('g').attr('clip-path', 'url(#chart-clip)');

      // Свечение
      g.append('path')
        .datum(data)
        .attr('fill', 'none')
        .attr('stroke', color)
        .attr('stroke-width', 10)
        .attr('stroke-opacity', 0.1)
        .attr('d', line)
        .attr('filter', 'url(#glow)');

      // Основная линия
      g.append('path')
        .datum(data)
        .attr('fill', 'none')
        .attr('stroke', color)
        .attr('stroke-width', 2.5)
        .attr('d', line);

      // Точки
      g.selectAll(`.dot-${label}`)
        .data(data)
        .enter()
        .append('circle')
        .attr('cx', (d: GraphPoint) => xScale(d.x))
        .attr('cy', (d: GraphPoint) => yScale(d.y))
        .attr('r', 4.5)
        .attr('fill', color)
        .attr('stroke', 'rgba(255,255,255,0.2)')
        .attr('stroke-width', 1)
        .attr('filter', 'url(#glow)');

      // Свечение точек
      g.selectAll(`.dot-glow-${label}`)
        .data(data)
        .enter()
        .append('circle')
        .attr('cx', (d: GraphPoint) => xScale(d.x))
        .attr('cy', (d: GraphPoint) => yScale(d.y))
        .attr('r', 8)
        .attr('fill', color)
        .attr('fill-opacity', 0.15)
        .attr('stroke', 'none');
    };

    // Рисуем синий график (baseline)
    drawNeonLine(this.baselineData, '#00D4FF', 'current');

    // Рисуем оптимизированный (зеленый или красный)
    if (this.optimizedData && this.optimizedData.length > 0 && this.isOptimized) {
      const optColor = this.isImprovement ? '#00E676' : '#FF1744';
      drawNeonLine(this.optimizedData, optColor, 'optimized');
    }

    // Легенда
    const legend = svg.append('g')
      .attr('transform', `translate(${innerWidth + 30}, 20)`);

    legend.append('line')
      .attr('x1', 0)
      .attr('y1', 0)
      .attr('x2', 25)
      .attr('y2', 0)
      .attr('stroke', '#00D4FF')
      .attr('stroke-width', 3);

    legend.append('text')
      .attr('x', 35)
      .attr('y', 4)
      .style('font-size', '13px')
      .style('fill', '#ccc')
      .style('font-weight', '500')
      .text('Текущий');

    if (this.optimizedData && this.optimizedData.length > 0 && this.isOptimized) {
      const optColor = this.isImprovement ? '#00E676' : '#FF1744';
      const optLabel = this.isImprovement ? 'Оптимизированный ✓' : 'Оптимизированный ✗';
      
      legend.append('line')
        .attr('x1', 0)
        .attr('y1', 25)
        .attr('x2', 25)
        .attr('y2', 25)
        .attr('stroke', optColor)
        .attr('stroke-width', 3);

      legend.append('text')
        .attr('x', 35)
        .attr('y', 29)
        .style('font-size', '13px')
        .style('fill', '#ccc')
        .style('font-weight', '500')
        .text(optLabel);

      legend.append('text')
        .attr('x', 35)
        .attr('y', 54)
        .style('font-size', '11px')
        .style('fill', '#888')
        .style('font-weight', '400')
        .text(`Метод: ${this.appliedMethod.toUpperCase()}`);
    }

    // Заголовок
    svg.append('text')
      .attr('x', innerWidth / 2)
      .attr('y', -20)
      .attr('text-anchor', 'middle')
      .style('font-size', '20px')
      .style('font-weight', '700')
      .style('fill', '#ffffff')
      .style('letter-spacing', '0.5px')
      .text('Потребление водорода');
  }
}