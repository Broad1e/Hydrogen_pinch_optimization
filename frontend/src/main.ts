import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { AppComponent } from './app/app.component';  // ← ИМПОРТИРУЕМ AppComponent

bootstrapApplication(AppComponent, appConfig)        // ← ИСПОЛЬЗУЕМ AppComponent
  .catch((err) => console.error(err));