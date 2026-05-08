import { bootstrapApplication } from '@angular/platform-browser';
import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { config } from './app/app.config.server';

@Component({
    selector: 'app-root',
    standalone: true,
    imports: [RouterOutlet],
    template: '<router-outlet></router-outlet>'
})
export class RootComponent { }

const bootstrap = () => bootstrapApplication(RootComponent, config);

export default bootstrap;
