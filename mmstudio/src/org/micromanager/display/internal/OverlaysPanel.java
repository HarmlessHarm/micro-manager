///////////////////////////////////////////////////////////////////////////////
//PROJECT:       Micro-Manager
//SUBSYSTEM:     Display implementation
//-----------------------------------------------------------------------------
//
// AUTHOR:       Chris Weisiger, 2015
//
// COPYRIGHT:    University of California, San Francisco, 2015
//
// LICENSE:      This file is distributed under the BSD license.
//               License text is included with the source distribution.
//
//               This file is distributed in the hope that it will be useful,
//               but WITHOUT ANY WARRANTY; without even the implied warranty
//               of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
//
//               IN NO EVENT SHALL THE COPYRIGHT OWNER OR
//               CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
//               INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES.

package org.micromanager.display.internal;

import com.google.common.eventbus.EventBus;
import com.google.common.eventbus.Subscribe;

import ij.ImagePlus;

import java.util.ArrayList;

import javax.swing.JPanel;

import net.miginfocom.swing.MigLayout;

import org.micromanager.data.Image;
import org.micromanager.display.DisplayWindow;
import org.micromanager.display.OverlayPanel;
import org.micromanager.display.internal.events.CanvasDrawEvent;
import org.micromanager.display.internal.events.LayoutChangedEvent;

/**
 * This class contains panels used to draw overlays on the image canvas.
 */
class OverlaysPanel extends JPanel {
   private ArrayList<OverlayPanel> panels_;
   private DisplayWindow display_;
   private MMVirtualStack stack_;
   private ImagePlus plus_;
   private EventBus displayBus_;
   
   public OverlaysPanel(DisplayWindow display, MMVirtualStack stack, ImagePlus plus,
         EventBus displayBus) {
      setLayout(new MigLayout("flowy"));
      display_ = display;
      stack_ = stack;
      plus_ = plus;
      displayBus_ = displayBus;

      displayBus_.register(this);

      panels_ = new ArrayList<OverlayPanel>();
      ScaleBarOverlayPanel scalebar = new ScaleBarOverlayPanel(display_);
      scalebar.setBus(displayBus_);
      panels_.add(scalebar);
      TimestampOverlayPanel timestamp = new TimestampOverlayPanel();
      timestamp.setBus(displayBus_);
      panels_.add(timestamp);

      redoLayout();
   }

   private void redoLayout() {
      removeAll();
      for (OverlayPanel panel : panels_) {
         add(panel);
      }
      displayBus_.post(new LayoutChangedEvent());
   }

   @Subscribe
   public void onCanvasDraw(CanvasDrawEvent event) {
      Image image = display_.getDatastore().getImage(stack_.getCurrentImageCoords());
      for (OverlayPanel panel : panels_) {
         panel.drawOverlay(event.getGraphics(), display_, image,
               event.getCanvas());
      }
   }

   public void cleanup() {
      displayBus_.unregister(this);
   }
}
