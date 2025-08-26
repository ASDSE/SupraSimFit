import os
import tkinter as tk

from core.fitting.dba_merge import run_dba_merge_fits
from gui.base_gui import BaseAppGUI

from core.progress_window import ProgressWindow


class DBAMergeFitsApp(BaseAppGUI):
    def __init__(self, root):
        super().__init__(root, title="DBA Merge Fits Interface")
        self.results_dir_var = self.add_string_var("results_dir", "")
        self.outlier_threshold_var = self.add_double_var("outlier_threshold", 0.25)
        self.rmse_threshold_factor_var = self.add_double_var("rmse_threshold_factor", 3)
        self.kd_threshold_factor_var = self.add_double_var("kd_threshold_factor", 3)
        self.enable_save_plots = self.add_bool_var("enable_save_plots", False)
        self.save_plots_dir = self.add_string_var("save_plots_dir", "")
        self.enable_display_plots = self.add_bool_var("display_plots", True)
        self.enable_save_results = self.add_bool_var("enable_save_results", False)
        self.save_results_dir = self.add_string_var("save_results_dir", "")
        self.plot_title_var = self.add_string_var("plot_title", "")

        pad_x = self.pad_x
        pad_y = self.pad_y

        self.results_dir_entry, self.results_dir_button = self.add_directory_selector(
            row=0, label_text="Results Directory:", var=self.results_dir_var
        )
        self.plot_title_entry = self.add_labeled_entry(
            row=1, label_text="Plot Title:", var=self.plot_title_var
        )
        self.outlier_threshold_entry = self.add_labeled_entry(
            row=2,
            label_text="Outlier Relative Threshold:",
            var=self.outlier_threshold_var,
        )
        self.rmse_threshold_factor_entry = self.add_labeled_entry(
            row=3,
            label_text="RMSE Threshold Factor:",
            var=self.rmse_threshold_factor_var,
        )
        self.kd_threshold_factor_entry = self.add_labeled_entry(
            row=4, label_text="Kd Threshold Factor:", var=self.kd_threshold_factor_var
        )
        self.save_plots_entry, self.save_plots_button = (
            self.add_toggleable_dir_selector(
                row=5,
                label_text="Save Plots To",
                bool_var=self.enable_save_plots,
                dir_var=self.save_plots_dir,
                input_file_var=self.results_dir_var,
            )
        )
        self.save_results_entry, self.save_results_button = (
            self.add_toggleable_dir_selector(
                row=7,
                label_text="Save Results To",
                bool_var=self.enable_save_results,
                dir_var=self.save_results_dir,
                input_file_var=self.results_dir_var,
            )
        )
        tk.Checkbutton(
            self.root, text="Display Plots", variable=self.enable_display_plots
        ).grid(row=8, column=0, columnspan=3, sticky=tk.W, padx=pad_x, pady=pad_y)
        
        tk.Button(self.root, text="Run Merge Fits", command=self.run_merge_fits).grid(
            row=9, column=0, columnspan=3, pady=10, padx=pad_x
        )
        self.lift_and_focus()

    def run_merge_fits(self):
        try:
                results_dir = self.results_dir_var.get()
                outlier_relative_threshold = self.outlier_threshold_var.get()
                rmse_threshold_factor = self.rmse_threshold_factor_var.get()
                kd_threshold_factor = self.kd_threshold_factor_var.get()
                save_plots = self.enable_save_plots.get()
                display_plots = self.enable_display_plots.get()
                save_results = self.enable_save_results.get()
                results_save_dir = self.save_results_dir.get()
                plot_title = self.plot_title_var.get()
                
                # Show a progress indicator
                with ProgressWindow(
                    self.root,
                    "Merging Fits in Progress",
                    "Merging fits in progress, please wait...",
                ) as progress_window:
                    run_dba_merge_fits(
                        results_dir,
                        outlier_relative_threshold,
                        rmse_threshold_factor,
                        kd_threshold_factor,
                        save_plots,
                        display_plots,
                        save_results,
                        results_save_dir,
                        plot_title,
                    )
                self.show_message("Merging fits completed!", is_error=False)

        except Exception as e:
            self.show_message(f"Error: {str(e)}", is_error=True)

if __name__ == "__main__":
    root = tk.Tk()
    DBAMergeFitsApp(root)
    root.mainloop()
